"""Audit hand_v1 against plan 3.4 using built gold/labels, not meta.boundary_rule claims.

Run from the repository root:
  python metric-detection/scripts/ml_train_hand_report.py [--json] [--out PATH]
The default inputs are templates/ml_train/hand_v1.jsonl and data_test/sessions_ml_hand_v1.jsonl.
Counts of boundary cases are distinct final gold spans; propagation counts are distinct sessions.
Negatives in the coverage table are all non-mask label positions in those sessions and may overlap rows.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

import ml_train_build as B
from label_rules import classify, exclusion_kind, is_common

BASE = Path(__file__).resolve().parents[1]
TARGETS = {
    'quoted': ('따옴표 안쪽', 300, 'span'),
    'trailing_punct': ('뒤따르는 문장 부호', 300, 'span'),
    'value_ends_punct': ('값 자체가 문장 부호로 끝남', 300, 'span'),
    'bearer': ('Bearer 스킴', 200, 'span'),
    'basic': ('Basic 스킴 (base64 전체)', 200, 'span'),
    'token_scheme': ('token 스킴', 200, 'span'),
    'url_password': ('URL 속 비밀번호·토큰 (스킴 ≥ 6종)', 400, 'span'),
    'user_colon_password': ('user:password', 200, 'span'),
    'connection_string': ('연결 문자열 Password=…;', 200, 'span'),
    'cookie': ('인증 쿠키와 속성', 200, 'span'),
    'pem_full': ('PEM 전체', 150, 'span'),
    'pem_truncated': ('잘린 PEM (본문 포함)', 150, 'span'),
    'pem_json_escaped': ('JSON 이스케이프 PEM', 150, 'span'),
    'wrapped': ('줄바꿈으로 끊긴 값', 150, 'span'),
    'base64': ('base64 인코딩', 150, 'span'),
    'url_encoded': ('URL 인코딩', 150, 'span'),
    'json_escaped': ('JSON 인코딩', 150, 'span'),
    'merged': ('맞닿은 값 병합', 100, 'span'),
    'common_value_both_positions': ('흔한 값: 자격증명·일반 자리', 400, 'session'),
    'distinct_value_repeated_in_logs': ('고유값: 로그 재등장', 600, 'session'),
    'distinct_value_in_identifier': ('고유값: 식별자 재등장 (음성)', 150, 'session'),
}


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def similar_items(templates):
    """Exact counterpart of a MinHash candidate check, feasible for just 160 templates.

    Mask values and numbers, then compare sets of five-token shingles (punctuation is a token).
    Exact Jaccard avoids approximate candidate retrieval misses on this small source set.
    Return locations only, never texts or values.
    """
    items = []
    for row in templates:
        for iid,item in enumerate(row['items']):
            normalized = re.sub(r'\d+', 'N', B.PLACEHOLDER.sub('VALUE',item['text']))
            tokens = re.findall(r'\w+|[^\w\s]',normalized.lower())
            shingles = {tuple(tokens[i:i+5]) for i in range(max(1,len(tokens)-4))}
            items.append((row['session_id'],row['meta']['split'],iid,shingles))
    hits = []
    for i,left in enumerate(items):
        for right in items[i+1:]:
            if left[1] == right[1]:
                continue
            union = left[3] | right[3]
            similarity = len(left[3] & right[3]) / len(union) if union else 1.0
            if similarity >= .8:
                hits.append({'left':[left[0],left[2]],'right':[right[0],right[2]],
                             'jaccard':round(similarity,4)})
    return hits


def static_checks(templates):
    """Hand source contract; the LLM card schema is deliberately not applied to authored sessions."""
    errors = []
    import ml_train_write as W
    required = {'split', 'group_id', 'variants', 'value_profile', 'boundary_rule', 'negatives', 'generator'}
    ood = {'twilio_auth_token', 'twilio_api_key', 'datadog_api_key', 'datadog_app_key',
           'huggingface_token', 'azure_storage_key'}
    seen = set()
    for row in templates:
        sid, meta = row['session_id'], row['meta']
        if sid in seen or not sid.startswith('hand-') or not meta['group_id'].startswith('hand-'):
            errors.append(f'{sid}: duplicate or non-hand id')
        seen.add(sid)
        if set(meta) != required or meta['value_profile'] != 'mltrain' or meta['variants'] != 5:
            errors.append(f'{sid}: unexpected meta contract')
        if meta['generator'].get('method') != 'hand_authored' or meta['split'] not in {'train','val','test'}:
            errors.append(f'{sid}: generator/split contract')
        texts = [item['text'] for item in row['items']]
        # The LLM helper mistakes the six letters in "Authorization: Bearer {{...}}" for a value.
        # Remove a scheme only when the following value is an actual placeholder, retaining literal checks.
        checked_texts = [re.sub(r'(?i)(\bAuthorization:\s*)(?:Bearer|Basic|token)(\s+)(?=\{\{)',
                                r'\1\2', text) for text in texts]
        errors.extend(f'{sid}: {error}' for error in W.literal_secrets(checked_texts))
        for text in texts:
            if re.search(r'\b(?:Jupyter|Terraform\s+(?:state|plan)|mcp_result)\b', text, re.I):
                errors.append(f'{sid}: OOD context')
            for match in B.PLACEHOLDER.finditer(text):
                if match.group('kind') in ood or any(f'of={k}' in match.group(0) for k in ood):
                    errors.append(f'{sid}: OOD kind')
    if len(templates) != 160:
        errors.append(f'expected 160 templates, got {len(templates)}')
    splits = Counter(t['meta']['split'] for t in templates)
    groups = {t['meta']['group_id'] for t in templates}
    if splits != {'train':128,'val':16,'test':16} or len(groups) != 160:
        errors.append(f'expected 128/16/16 distinct groups, got {dict(splits)} / {len(groups)}')
    return errors


def audit(template_path, sessions_path):
    templates, sessions = read(template_path), read(sessions_path)
    _, gold_path, labels_path = B.paths_of(sessions_path)
    gold, labels = read(gold_path), read(labels_path)
    errors = static_checks(templates)
    duplicates = similar_items(templates)
    if duplicates:
        errors.append(f'{len(duplicates)} cross-split item pairs have normalized Jaccard >= 0.8')
    by_sid = {t['session_id']: t for t in templates}
    gold_by_item, labels_by_session = defaultdict(list), defaultdict(list)
    for row in gold:
        gold_by_item[row['session_id'],row['item_id']].append(row['span'])
    for row in labels:
        if row['kind'] != B.MASK:
            labels_by_session[row['session_id']].append(row)
    hits = {rule: set() for rule in TARGETS}
    rule_sessions = {rule: set() for rule in TARGETS}
    schemes = set()
    for session in sessions:
        sid = session['session_id']
        template_id = sid.rsplit('~',1)[0]
        template = by_sid[template_id]
        seed = f"{session['meta']['split']}:{template_path.stem}:{template_id}~{session['meta']['variant']}"
        raw = B.render_session(template['items'], seed, 'mltrain')
        positions = defaultdict(list)
        texts = {item['item_id']:item['text'] for item in session['items']}
        values = set()
        for iid, (text, raw_spans, _) in enumerate(raw):
            if texts[iid] != text:
                errors.append(f'{sid}/{iid}: source rendering differs')
            specs = [m for m in B.PLACEHOLDER.finditer(template['items'][iid]['text'])
                     if m.group('kind') not in {'neg','mask'} and '|as=' not in m.group(0)]
            if len(specs) != len(raw_spans):
                errors.append(f'{sid}/{iid}: cannot match placeholder provenance')
                continue
            for final in gold_by_item[sid,iid]:
                start, end = final['start'], final['end']
                value = text[start:end]
                values.add(value)
                positions[value].append((iid,start,end))
                before, after = text[:start], text[end:]
                key = (sid,iid,start,end)
                rules = set()
                quoted = bool(before and before[-1] in '\'"`' and after.startswith(before[-1]))
                if quoted:
                    rules.add('quoted')
                if after[:1] and after[0] in '.,;)]`*':
                    rules.add('trailing_punct')
                if quoted and value[-1] in '.,;)]`*':
                    rules.add('value_ends_punct')
                scheme = re.search(r'(?i)\b(Bearer|Basic|token)[ \t]+$', before)
                if scheme:
                    rules.add({'bearer':'bearer','basic':'basic','token':'token_scheme'}[scheme[1].lower()])
                _, position = classify(text,start,end)
                url = re.search(r'([a-z][\w+.-]*)://[^\s/:@\'"]*:$',before)
                if url and after.startswith('@'):
                    rules.add('url_password')
                    schemes.add(url[1])
                if position in {'user_colon_pw','curl_u','chpasswd','pgpass'}:
                    rules.add('user_colon_password')
                if re.search(r'(?i)\bPassword=$',before) and after.startswith(';'):
                    rules.add('connection_string')
                if re.search(r'(?i)(?:Cookie|Set-Cookie):[^\n]*\bsession=$',before):
                    rules.add('cookie')
                covered = [(spec,sp) for spec,sp in zip(specs,raw_spans)
                           if start <= sp['start'] < sp['end'] <= end]
                if len(covered) > 1:
                    rules.add('merged')
                transforms = {t.split('=',1)[0] for spec,_ in covered
                              for t in (spec.group('transforms') or '').split('|') if t}
                if value.startswith('-----BEGIN'):
                    if '\\n' in value:
                        rules.add('pem_json_escaped')
                    elif '-----END ' in value:
                        rules.add('pem_full')
                    elif '\n' in value and value.split('\n',1)[1].strip():
                        rules.add('pem_truncated')
                if 'wrap' in transforms and '\n' in value:
                    rules.add('wrapped')
                if 'base64' in transforms:
                    rules.add('base64')
                if 'url' in transforms and re.search(r'%[0-9A-F]{2}',value):
                    rules.add('url_encoded')
                if 'json' in transforms and re.search(r'\\["\\nrt]',value):
                    rules.add('json_escaped')
                for rule in rules:
                    hits[rule].add(key)
                    rule_sessions[rule].add(sid)
        # Propagation is measured in sessions, with a positive occurrence and independently judged replay.
        for value, occurrences in positions.items():
            if not is_common(value) and len({p[0] for p in occurrences}) >= 2:
                if any(classify(texts[iid],start,end)[0] not in {'slot','ident'}
                       and not exclusion_kind(texts[iid],start,end) for iid,start,end in occurrences):
                    hits['distinct_value_repeated_in_logs'].add(sid)
                    rule_sessions['distinct_value_repeated_in_logs'].add(sid)
        for row in labels_by_session[sid]:
            if not row.get('replay'):
                continue
            value = texts[row['item_id']][row['start']:row['end']]
            if value not in values:
                errors.append(f'{sid}: replay has no exact positive counterpart')
            if is_common(value):
                rule = 'common_value_both_positions'
            elif row['kind'] == 'identifier':
                rule = 'distinct_value_in_identifier'
            else:
                continue
            hits[rule].add(sid)
            rule_sessions[rule].add(sid)
    if len(schemes) < 6:
        errors.append(f'URL schemes: {len(schemes)} < 6')
    coverage = []
    for rule,(title,target,unit) in TARGETS.items():
        count = len(hits[rule])
        if count < target:
            errors.append(f'{rule}: {count} < {target}')
        coverage.append({'rule':rule,'title':title,'unit':unit,'target':target,'actual':count,
                         'negative_positions_in_sessions':sum(len(labels_by_session[sid]) for sid in rule_sessions[rule])})
    return {'templates':len(templates),'sessions':len(sessions),'items':sum(len(s['items']) for s in sessions),
            'gold':len(gold),'negative_positions':sum(len(v) for v in labels_by_session.values()),
            'masks':sum(r['kind']==B.MASK for r in labels),'url_schemes':sorted(schemes),
            'groups_by_split':dict(Counter(t['meta']['split'] for t in templates)),
            'sessions_by_split':dict(Counter(s['meta']['split'] for s in sessions)),
            'cross_split_similar_items':duplicates,
            'negatives_by_kind':dict(sorted(Counter(r['kind'] for r in labels if r['kind']!=B.MASK).items())),
            'coverage':coverage,'errors':errors}


def markdown(report):
    out = ['# 손 템플릿 경계·퍼뜨림 커버리지', '',
           f"템플릿 {report['templates']}개, 세션 {report['sessions']}개, item {report['items']}개, "
           f"정답 {report['gold']} span, 음성 {report['negative_positions']}곳, mask {report['masks']}곳.", '',
           'split은 group 128/16/16, 세션 640/80/80 (train/val/test)이다.', '',
           '규칙은 실제 빌드된 정답 span과 labels로 집계한다. 경계는 span 수, 퍼뜨림은 세션 수다. '
           '한 span·세션이 여러 규칙에 집계될 수 있다. 음성 열은 해당 규칙을 충족한 세션 안의 모든 '
           '음성 위치 수이며 mask는 뺀다. 따라서 행 사이에서 중복되며, 규칙별 최소 음성 목표는 없다.', '',
           '| 규칙 | 단위 | 3.4절 최소 | 실제 | 해당 세션의 음성 위치 | 충족 |',
           '| --- | --- | ---: | ---: | ---: | :---: |']
    for row in report['coverage']:
        out.append(f"| {row['title']} | {row['unit']} | {row['target']} | {row['actual']} | "
                   f"{row['negative_positions_in_sessions']} | {'✓' if row['actual']>=row['target'] else '미달'} |")
    out += ['', 'URL 스킴: ' + ', '.join(report['url_schemes']) + '.', '',
            '| 음성 kind | 위치 수 |', '| --- | ---: |']
    out += [f'| `{kind}` | {n} |' for kind,n in report['negatives_by_kind'].items()]
    out += ['', '중복 검사: 값·숫자를 가린 item의 5-token shingle 집합을 전수 비교한다 '
            '(정확한 Jaccard, 기준 0.8). split 사이 유사 item 쌍 '
            f"{len(report['cross_split_similar_items'])}개.", '',
            f"검사 결과: {'통과' if not report['errors'] else '실패'}."]
    out += [f'- {error}' for error in report['errors']]
    return '\n'.join(out) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template',type=Path,default=BASE/'templates/ml_train/hand_v1.jsonl')
    parser.add_argument('--sessions',type=Path,default=BASE/'data_test/sessions_ml_hand_v1.jsonl')
    parser.add_argument('--json',action='store_true')
    parser.add_argument('--out',type=Path)
    args = parser.parse_args()
    report = audit(args.template,args.sessions)
    result = json.dumps(report,ensure_ascii=False,indent=2)+'\n' if args.json else markdown(report)
    if args.out:
        args.out.write_text(result)
    else:
        print(result,end='')
    raise SystemExit(bool(report['errors']))


if __name__ == '__main__':
    main()
