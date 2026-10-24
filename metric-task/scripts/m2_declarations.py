"""Strict declaration audit for scenarios; read-only/non-blocking legacy audit via CLI.

Find candidates independently of declared values, combine installed gitleaks with credential
slot/URL/auth/cookie/CLI/PEM/provider extraction, then apply metric-detection label_rules.
No extension filter. Scan session inputs, generated files, local git metadata and every
historical blob/message, including deleted files. Diagnostics never print candidate values.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'metric-detection'/'scripts'))
import label_rules as labels


@dataclass(frozen=True)
class Candidate:
    start: int
    end: int
    source: str


# Prefix patterns only discover candidates; label_rules determines contextual exclusions.
PROVIDER=re.compile(r'(?<![\w])(?:github_pat_[A-Za-z0-9_]{35,}|gh[pousr]_[A-Za-z0-9]{30,}|glpat-[A-Za-z0-9_-]{20,}|npm_[A-Za-z0-9]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|[sp]k_(?:live|test)_[A-Za-z0-9]{20,}|whsec_[A-Za-z0-9]{20,}|GOCSPX-[A-Za-z0-9_-]{20,}|dckr_pat_[A-Za-z0-9_-]{20,}|hvs\.[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|https://hooks\.slack\.com/services/[^\s\"\'<>]+)')
PEM=re.compile(r'-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----(?:(?!-----END)[\s\S])+?-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----')
ASSIGN=re.compile(r'''(?im)(?P<key>[A-Za-z_][\w.-]*)["']?\s*[:=]\s*(?P<value>"(?:\\.|[^"\\\n])*"|'[^'\n]*'|[^\s,;\n]+)''')
AUTH=re.compile(r'(?i)(?:Authorization["\']?\s*[:=]\s*["\']?|PRIVATE-TOKEN:\s*)(?:(?:Bearer|Basic|token)\s+)?([^\s"\'\r\n]+)')
URL=re.compile(r'[a-z][\w+.-]*://[^\s/:@"\']+:([^\s@"\']+)@')
COOKIE=re.compile(r'(?i)\b(?:session(?:_?id)?|auth(?:_token)?|access_token|refresh_token)=([^\s;"\']+)')
CLI=re.compile(r'''(?i)(?:--(?:password|passwd|pass|requirepass|token|api-key|secret)(?:=|\s+)|sshpass\s+-p\s+|docker\s+login[^\n]*?\s-p\s+)("(?:\\.|[^"\\])*"|'[^']*'|[^\s;|]+)''')
XML_SLOT=re.compile(r'(?is)<(?:[\w.-]+:)?(?:password|passwd|pass|secret|api[_-]?key|private[_-]?key|token)(?:\s[^>]*)?>([^<]+)</')
KO_PROSE=re.compile(r'(?:비번|비밀번호|API\s*키|토큰|시크릿)(?:은|는|이|가)?\s*[:=]?\s*[`\"\']([^`\"\'\n]+)[`\"\']')
PROSE=re.compile(r'''(?i)(?:password\s+(?:is|was)|(?:API key|token|secret)\s+is)\s+["'`]?([^\s"'`,;]+)''')
CREDENTIAL_KEY=re.compile(r'(?i)(?:password|passwd|passphrase|(?:^|_)pass$|(?:^|_)pwd$|secret|(?:^|_)token$|api[_-]?key|access[_-]?key|account[_-]?key|private[_-]?key|(?:^|_)auth(?:token)?$|credential)')
# These keys denote documented structure, not literal authentication material. A value that
# has its own provider shape still goes through PROVIDER extraction independently.
STRUCTURAL_KEY=re.compile(r'(?i)(?:_display|_min_length|_max_length|_ttl(?:_seconds)?|_path|_file|_sha256|_hash|_name|_type|_format|_count)$|^(?:max_tokens|token_ttl_seconds)$')
IDENT_KEY=re.compile(r'(?i)(?:client_?id|request_?id|resource_?id|source_commit|commit_hash|username|user|host|project_id|client_email)$')


def candidates(text):
    found={}
    def add(start,end,source):
        start,end=labels.normalize_span(text,start,end)
        if end>start: found[(start,end)]=Candidate(start,end,source)
    blocks=[]
    for m in PEM.finditer(text):
        add(m.start(),m.end(),'pem'); blocks.append((m.start(),m.end()))
    for regex,name,group in [(PROVIDER,'provider',0),(URL,'url_password',1),(AUTH,'authorization',1),
                              (COOKIE,'cookie',1),(CLI,'cli',1),(PROSE,'prose',1),(KO_PROSE,'korean_prose',1),(XML_SLOT,'xml_slot',1)]:
        for m in regex.finditer(text):
            a,b=m.span(group)
            if text[a:a+1] in ('"',"'"): a,b=a+1,b-1
            add(a,b,name)
    for m in ASSIGN.finditer(text):
        key=m['key']
        if not CREDENTIAL_KEY.search(key) or STRUCTURAL_KEY.search(key) or IDENT_KEY.search(key): continue
        a,b=m.span('value')
        if text[a:a+1] in ('"',"'"): a,b=a+1,b-1
        if any(x<=a and b<=y for x,y in blocks): continue
        add(a,b,'assignment')
    # Never count a PEM body/quoted escaped block twice as a partial assignment.
    return sorted(found.values(),key=lambda c:(c.start,c.end))


def validated_exclusion(text,c):
    """Only exclusions evidenced by the span and its immediate context are accepted.

    In particular label_rules.code's generic dotted expression heuristic must not hide an
    unquoted high-entropy Vault credential, and metadata is not a global allowlist.
    """
    value=text[c.start:c.end]
    # These precise semantic positions are expressly non-credentials in LABELING.md.
    before=text[max(0,c.start-100):c.start]
    if re.search(r'''(?i)\b(?:csrf|xsrf)[_-]?token["']?\s*[:=]\s*["']?$''',before):
        return 'non_credential'
    if re.search(r'''(?i)\b(?:request[_-]?id|client[_-]?id|commit[_-]?hash)["']?\s*[:=]\s*["']?$''',before):
        return 'identifier'
    kind=labels.exclusion_kind(text,c.start,c.end)
    if kind=='code' and c.source in {'provider','authorization','cookie','url_password','pem','xml_slot','assignment','cli','korean_prose'}:
        # Obvious variable references remain excluded; a provider-shaped literal does not.
        if re.match(r'^(?:\$|process\.env\b|os\.environ\b|self\.|this\.)',value): return 'reference'
        # Entity/JSON escapes are literal visible surface forms in credential slots.
        if c.source == 'xml_slot' or re.search(r'&(?:amp|lt|gt|quot);|\\u00[0-9a-fA-F]{2}', value): return None
        if re.match(r'^(?:true|false|null|none|nil|undefined)$',value,re.I): return 'code'
        if re.search(r'^(?:[A-Za-z_$][\w.$]*[([]|[{}]$)',value): return 'code'
        if re.match(r'^(?:\$|process\.env\b|os\.environ\b|self\.|this\.)',value): return 'reference'
        return None
    return kind


def audit_text(text,declared, *, use_gitleaks=True):
    problems=[]; cs=candidates(text)
    for c in cs:
        value=text[c.start:c.end]
        verdict,_=labels.classify(text,c.start,c.end)
        excluded=validated_exclusion(text,c)
        if excluded: continue
        # Each extractor already supplies evidence of a credential position or provider format.
        if value not in declared:
            line=text.count('\n',0,c.start)+1
            problems.append(f'line {line}: undeclared {c.source} candidate ({verdict}, {len(value)} chars)')
    if use_gitleaks:
        exe=shutil.which('gitleaks')
        if not exe: return problems  # caller reports optional scanner coverage as skipped
        proc=subprocess.run([exe,'stdin','--no-banner','--report-format','json','--report-path','-','--exit-code','0'],
                            input=text,text=True,capture_output=True)
        try: rows=json.loads(proc.stdout or '[]')
        except json.JSONDecodeError: return problems+['gitleaks output was not JSON']
        if proc.returncode: problems.append('gitleaks execution failed')
        for row in rows:
            value=row.get('Secret','')
            # Gitleaks may return a URL container or include a suffix after a precise provider
            # match. Resolve to the independently extracted span covering this same location.
            starts=[m.start() for m in re.finditer(re.escape(value),text)] if value else []
            for start in starts:
                end=start+len(value)
                overlaps=[c for c in cs if c.start == start and c.end == end]
                url_match=URL.fullmatch(value)
                if url_match:
                    overlaps += [c for c in cs if c.source == 'url_password' and c.start == start+url_match.start(1) and c.end == start+url_match.end(1)]
                if overlaps:
                    # Independently audited precise spans, not arbitrary substring acceptance.
                    continue
                c=Candidate(start,end,'gitleaks:'+row.get('RuleID','unknown'))
                if not validated_exclusion(text,c) and value not in declared:
                    problems.append(f"line {text.count(chr(10),0,start)+1}: undeclared {c.source} candidate")
    return sorted(set(problems))


def surfaces(task,ws):
    """Labels and values in memory only; no scanner scratch file with plaintext values."""
    result={}
    for path in sorted(ws.rglob('*')):
        if not path.is_file() or '.git' in path.relative_to(ws).parts: continue
        try: text=path.read_bytes().decode('utf-8')
        except UnicodeDecodeError: continue
        result['file:'+path.relative_to(ws).as_posix()]=text
    fields=['prompt','session_env','append_system_prompt','mcp_fixture','history','final_commit','worktree_changes','setup']
    import m2_tasks as mt
    for field in fields:
        # Preserve string text rather than wrapping in JSON, which would invent extra escapes.
        for i,text in enumerate(mt.strings(task.fill_any(task.spec.get(field,{})))):
            result[f'spec:{field}:{i}']=text
    # Environment and argv carry credential names outside the individual string value.
    # Reconstruct that actual shell/CLI context as well as scanning each raw string.
    for key,value in task.fill_any(task.spec.get('session_env',{})).items():
        result['spec:session_env:key:'+key]=key+'='+value
    for i,argv in enumerate(task.fill_any(task.spec.get('setup',[]))):
        result[f'spec:setup:argv:{i}']=' '.join(argv)
    log=mt.git(ws,'log','--all','--format=%H',check=False)
    for commit in log.stdout.splitlines():
        result['git:message:'+commit]=mt.git(ws,'show','-s','--format=%B',commit).stdout
        entries=mt.git(ws,'ls-tree','-r','--name-only',commit).stdout.splitlines()
        for rel in entries:
            try:
                result[f'git:{commit}:{rel}']=mt.git(ws,'show',commit+':'+rel).stdout
            except UnicodeDecodeError:
                continue  # binary blobs are copied by build, not treated as text credentials
    result['git:config']=mt.git(ws,'config','--local','--list').stdout
    return result


def audit_task(task,ws, *, use_gitleaks=True):
    declared={s.value for s in task.secrets.values()}
    problems=[]
    for name,s in task.secrets.items():
        if len(s.value)<8 or labels.is_common(s.value): problems.append(f'secret {name}: shorter than 8 or common')
    # Batch scanner per surface: prevents fragments in large stdin from losing a provider key.
    texts=surfaces(task,ws)
    for surface,text in texts.items():
        problems.extend(surface+': '+p for p in audit_text(text,declared,use_gitleaks=use_gitleaks))
    return problems


def main():
    import m2_tasks as mt
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--tasks',nargs='+',default=['scenarios'])
    p.add_argument('--legacy-audit',action='store_true',help='report legacy inconsistencies without failing')
    a=p.parse_args(); total=0
    if not shutil.which('gitleaks'):
        print('gitleaks: skipped (not installed); candidate extraction and label_rules checks remain enabled')
    for task in mt.load_tasks(a.tasks):
        with tempfile.TemporaryDirectory() as d:
            ws=Path(d)/'workspace'; mt.build(task,ws); problems=audit_task(task,ws)
        total+=len(problems)
        print(f'{task.id}: {len(problems)} declaration problem(s)')
        for problem in problems: print('  '+problem)
    raise SystemExit(0 if a.legacy_audit else bool(total))

if __name__=='__main__': main()
