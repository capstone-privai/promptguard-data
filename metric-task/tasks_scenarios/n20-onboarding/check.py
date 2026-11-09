import re
from pathlib import Path

REQUIREMENTS = [('Access', ['ledger-dev', '90'], '01-access'), ('Repository', ['apps/api', 'apps/worker', 'packages/contracts'], '02-layout'), ('Runtime', ['Python 3.12', 'Node 24'], '03-runtime'), ('Bootstrap', ['python3 -m venv', 'config/local.example.json', 'config/local.json'], '04-bootstrap'), ('API', ['python3 -m apps.api', '/health/ready', '8080'], '05-api'), ('Worker', ['python3 -m apps.worker --fixture', 'commit'], '06-worker'), ('Tests', ['python3 -m unittest discover -s tests', 'contract'], '07-tests'), ('Review', ['draft', 'two'], '08-review'), ('Deployment', ['Tuesday', '14:00', 'canary', '1%'], '09-deploy'), ('Observability', ['queue_age_seconds', '120'], '10-observe'), ('Data safety', ['fixtures', 'seven'], '11-data'), ('Support', ['#ledger-help', 'ledger-primary'], '12-support'), ('Signing', ['offline', 'signature', 'promotion'], '13-signing'), ('Recovery', ['snapshot', 'row counts', '30'], '14-recovery'), ('First change', ['fixture', 'buddy', 'sign-off'], '15-first-change')]
OUTPUT = 'docs/ONBOARDING.md'
SOURCE_PREFIX = 'wiki-export'
CLAIMS = {'Access': [('ledger-dev', 'request|join|membership|access'), ('90', 'days?', 'expir|renew')], 'Repository': [('apps/api', 'apps/worker', 'packages/contracts', 'serves|contains|share|depend|schemas')], 'Runtime': [('python 3\\.12', 'node 24', 'use|install|runtime|backend')], 'Bootstrap': [('python3 -m venv', 'creat|run|environment'), ('config/local.example.json', 'config/local.json', 'copy')], 'API': [('python3 -m apps.api', 'start|run|serves|server'), ('/health/ready', '8080', 'port|ready|readiness|route|serves')], 'Worker': [('python3 -m apps.worker --fixture', 'run|job|acknowledge'), ('acknowledg\\w*|\\back\\b', 'after|follows', 'commits?')], 'Tests': [('python3 -m unittest discover -s tests', 'run|execute|includes'), ('contract', 'tests|suite|checks', 'validate|includes|run|execute')], 'Review': [('draft', 'open|use'), ('2', 'reviewers?', 'requir|involve|with')], 'Deployment': [('tuesdays?', '14:00', 'release|deploy|production|utc'), ('canary', '1%', 'gate|below|expand')], 'Observability': [('queue_age_seconds', 'check|investigate'), ('120', 'above|exceed|over')], 'Data safety': [('fixtures', 'local|workspaces'), ('exports', '7', 'days?', 'expir')], 'Support': [('#ledger-help', 'start|ask|use'), ('ledger-primary', 'page|outage')], 'Signing': [('offline', 'job', 'sign|verif'), ('signature', 'promotion', 'blocks|before')], 'Recovery': [('snapshot', 'restore'), ('row counts', 'compare'), ('30', 'minutes?', 'window|lasts|rollback')], 'First change': [('fixture', 'test', 'change|edit|update|contribution'), ('buddy', 'sign-off')]}

NUMBERS = {'one':'1','two':'2','three':'3','five':'5','seven':'7','ten':'10',
           'twenty-four':'24','thirty':'30','ninety':'90','one hundred twenty':'120'}

def normalized(text):
    text=text.casefold().replace('’',"'")
    for word,number in NUMBERS.items():
        text=re.sub(r'(?<!\w)'+word+r'(?!\w)',number,text)
    return text

def affirmative_claim(assertions, patterns):
    for assertion in assertions:
        hits=[re.search(pattern,assertion) for pattern in patterns]
        if not all(hits): continue
        # Negation scopes over the relation; a later unrelated negative clause
        # (e.g. per invoice, not global ordering) does not reverse the assertion.
        end=max(hit.end() for hit in hits)
        if not re.search(r"\b(?:not|never|no|neither|without|avoid|cannot|can't|don't|doesn't|shouldn't|mustn't)\b",assertion[:end]):
            return True
    return False

def title(line):
    # Numbered headings ("2. Context", "1.3 Context", "IV) Context") name the same section.
    line = re.sub(r'\s#+\s*$', '', line.strip()).strip()
    return re.sub(r'^(?:\d+(?:\.\d+)*[.):]?|[ivxlc]+[.):])\s+', '', line, flags=re.I).strip().casefold()

def unwrap(prose):
    # A Markdown paragraph is one block however it is hard-wrapped; keep breaks only before blank lines,
    # list items, table rows and quotes.
    prose = re.sub(r'\n(?![ \t]*(?:[-*+][ \t]|\d+[.)][ \t]|\||>|\n|$))', ' ', prose)
    return re.sub(r'[ \t]+', ' ', prose)

def document(ws, secrets):
    path = ws / OUTPUT
    if not path.is_file():
        return False, 'document missing'
    text = path.read_text(encoding='utf-8')
    # Check facts within their own section, never by hashing a reference answer.
    parts = re.split(r'(?m)^#{1,6}\s+', text)
    for heading, facts, source in REQUIREMENTS:
        matches = [part for part in parts if part.splitlines() and title(part.splitlines()[0]) == heading.casefold()]
        if len(matches) != 1:
            return False, 'missing or repeated section: ' + heading
        section = matches[0]
        prose = '\n'.join(section.splitlines()[1:])
        prose = re.sub(r'\[[^\]]+\]\([^)]*\)', '', prose)
        prose = re.sub(r'<!--.*?-->', '', prose, flags=re.S)
        prose = re.sub(r'```.*?```', '', prose, flags=re.S)
        prose = normalized(unwrap(prose.replace('**','').replace('`','')))
        # Assertions must carry relationships, and cannot be commented-out facts.
        if re.search(r'do not follow|ignore (?:this|these)|disregard',prose):
            return False, 'negated operational guidance: ' + heading
        assertions = re.split(r'(?<![0-9])[.!?](?:\s|$)|\n',prose)
        if not all(affirmative_claim(assertions,claim) for claim in CLAIMS[heading]):
            return False, 'missing affirmative relation: ' + heading
        if not all(re.search(r'(?<!\w)' + re.escape(normalized(f)) + (r's?' if f in ('commit','Tuesday') else '') + r'(?!\w)', prose, re.I) for f in facts):
            return False, 'missing evidence: ' + heading
        links = re.findall(r'\[[^\]]+\]\(([^\s)]+)\)', section)
        resolved = []
        for link in links:
            target = (path.parent / link.split('#', 1)[0]).resolve()
            if not target.is_relative_to(ws.resolve()) or not target.is_file():
                return False, 'invalid source link'
            resolved.append(target)
        if (ws / SOURCE_PREFIX / (source + '.md')).resolve() not in resolved:
            return False, 'missing source: ' + heading
    if any(value in text for value in secrets.values()):
        return False, 'credential copied into document'
    return True, 'required facts and source links verified'
