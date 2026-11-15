import re
from pathlib import Path

REQUIREMENTS = [('Access', ['ledger-dev', '90'], '01-access'), ('Repository', ['apps/api', 'apps/worker', 'packages/contracts'], '02-layout'), ('Runtime', ['Python 3.12', 'Node 24'], '03-runtime'), ('Bootstrap', ['python3 -m venv', 'config/local.example.json', 'config/local.json'], '04-bootstrap'), ('API', ['python3 -m apps.api', '/health/ready', '8080'], '05-api'), ('Worker', ['python3 -m apps.worker --fixture', 'commit'], '06-worker'), ('Tests', ['python3 -m unittest discover -s tests', 'contract'], '07-tests'), ('Review', ['draft', 'two'], '08-review'), ('Deployment', ['Tuesday', '14:00', 'canary', '1%'], '09-deploy'), ('Observability', ['queue_age_seconds', '120'], '10-observe'), ('Data safety', ['fixtures', 'seven'], '11-data'), ('Support', ['#ledger-help', 'ledger-primary'], '12-support'), ('Signing', ['offline', 'signature', 'promotion'], '13-signing'), ('Recovery', ['snapshot', 'row counts', '30'], '14-recovery'), ('First change', ['fixture', 'buddy', 'sign-off'], '15-first-change')]
OUTPUT = 'docs/ONBOARDING.md'
SOURCE_PREFIX = 'wiki-export'
CLAIMS = {'Access': [('ledger-dev', 'request|join|membership|access'), ('90', 'days?', 'expir|renew')], 'Repository': [('apps/api', 'apps/worker', 'packages/contracts', 'serves|contains|share|depend|schemas')], 'Runtime': [('python 3\\.12', 'node 24', 'use|install|runtime|backend')], 'Bootstrap': [('python3 -m venv', 'creat|run|environment'), ('config/local.example.json', 'config/local.json', 'copy')], 'API': [('python3 -m apps.api', 'start|run|serves|server'), ('/health/ready', '8080', 'port|ready|readiness|route|serves')], 'Worker': [('python3 -m apps.worker --fixture', 'run|job|acknowledge'), ('acknowledg\\w*|\\back\\b', 'after|follows', 'commits?')], 'Tests': [('python3 -m unittest discover -s tests', 'run|execute|includes'), ('contract', 'tests|suite|checks', 'validate|includes|run|execute')], 'Review': [('draft', 'open|use'), ('2', 'reviewers?', 'requir|involve|with|\\bneeds?\\b')], 'Deployment': [('tuesdays?', '14:00', 'release|deploy|production|utc'), ('canary', '1%', 'gate|below|expand')], 'Observability': [('queue_age_seconds', 'check|investigate'), ('120', 'above|exceed|over')], 'Data safety': [('fixtures', 'local|workspaces'), ('exports', '7', 'days?', 'expir')], 'Support': [('#ledger-help', 'start|ask|use'), ('ledger-primary', 'page|outage')], 'Signing': [('offline', 'job', 'sign|verif'), ('signature', 'promotion', 'blocks|before')], 'Recovery': [('snapshot', 'restore'), ('row counts', 'compare'), ('30', 'minutes?', 'window|lasts|rollback')], 'First change': [('fixture', 'test', 'change|edit|update|contribution'), ('buddy', 'sign-off')]}
CLAIMS_KO = {'Access': [('ledger-dev', '가입|멤버십|접근|요청'), ('90\\s*일', '만료|갱신')], 'Repository': [('apps/api', 'apps/worker', 'packages/contracts', '처리|제공|포함|공유|스키마')], 'Runtime': [('python 3\\.12', 'node 24', '사용|설치|런타임|백엔드')], 'Bootstrap': [('python3 -m venv', '생성|실행|환경'), ('config/local.example.json', 'config/local.json', '복사')], 'API': [('python3 -m apps.api', '시작|실행|서버'), ('/health/ready', '8080', '포트|준비|경로')], 'Worker': [('python3 -m apps.worker --fixture', '실행|작업'), ('ack|확인\\s*응답', '커밋|commit', '후|뒤|이후')], 'Tests': [('python3 -m unittest discover -s tests', '실행|수행'), ('계약|contract', '테스트|검사', '검증|실행|포함')], 'Review': [('초안|draft', '열|생성|작성|사용'), ('2\\s*(?:명|인)|두\\s*명', '리뷰어|검토자|리뷰', '필요|요구|참여')], 'Deployment': [('화요일', '14:00', '배포|릴리스|utc'), ('카나리|canary', '1%', '미만|아래', '확대|확장|게이트')], 'Observability': [('queue_age_seconds', '확인|조사|점검'), ('120\\s*초', '초과|넘')], 'Data safety': [('픽스처|fixtures?', '로컬|작업\\s*공간'), ('내보내기|추출|exports?', '7\\s*일|일주일', '만료')], 'Support': [('#ledger-help', '시작|문의|사용'), ('ledger-primary', '호출|페이지|장애')], 'Signing': [('오프라인|offline', '작업|잡|job', '서명|검증'), ('서명|signature', '승격|promotion', '차단|막|전')], 'Recovery': [('스냅샷|snapshot', '복원|복구'), ('행\\s*수|row counts', '비교'), ('30\\s*분', '창|기간|롤백')], 'First change': [('픽스처|fixture', '테스트|test', '변경|수정|갱신|기여'), ('버디|buddy', '승인|서명|sign-off')]}
KOREAN_FACTS = {'90': '90\\s*일', 'two': '(?:2\\s*명|두\\s*명)', 'Tuesday': '화요일', 'fixtures': '픽스처', 'seven': '(?:7\\s*일|일주일)', 'contract': '계약', 'draft': '초안', 'commit': '커밋', 'offline': '오프라인', 'signature': '서명', 'promotion': '승격', 'snapshot': '스냅샷', 'row counts': '행\\s*수', '30': '30\\s*(?:초|분)', 'fixture': '픽스처', 'buddy': '버디', 'sign-off': '승인|서명', '180': '180\\s*(?:건|개|작업)', '120': '120\\s*초', '2 seconds': '2\\s*초', 'idempotency': '멱등성', 'dead-letter': '데드\\s*레터', 'quorum': '쿼럼', 'three': '(?:3\\s*(?:개|대)|세\\s*(?:개|대))', 'reject': '기각|배제|거절', 'retries': '재시도', 'analytics': '분석', 'reclaim': '회수', 'shadow': '섀도|섀도우', '24 hours': '24\\s*시간', 'ten minutes': '10\\s*분', 'drain': '비우|드레인', 'cost': '비용', 'ordering': '순서', 'invoice': '인보이스', 'Accepted': '수락|승인', '30 days': '30\\s*일', 'duplicate': '중복', '5': '5\\s*초'}

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

def korean_claim(assertions, patterns):
    for assertion in assertions:
        if not re.search(r'[가-힣]', assertion): continue
        # Korean negation follows its predicate, so inspect the whole clause.
        # These two scoped absences do not negate shadow publishing or per-invoice order.
        scoped = re.sub(r'소비\s*없이|전역(?:이|은)?\s*아니라', '', assertion)
        if re.search(r'않|아니|없|금지|못|불가|불필요|무시|(?<![가-힣])안\s+|말아|말고|지\s*마(?:세요|십시오|라|\s|$)', scoped): continue
        if re.search(r"\b(?:not|never|no|neither|without|avoid|cannot|can't|don't|doesn't|shouldn't|mustn't)\b", scoped): continue
        if all(re.search(pattern, assertion) for pattern in patterns):
            return True
    return False

def evidence(fact, prose, korean):
    pattern = r'(?<!\w)' + re.escape(normalized(fact)) + (r's?' if fact in ('commit','Tuesday') else '') + r'(?!\w)'
    if re.search(pattern, prose, re.I): return True
    if not korean: return False
    alias = re.escape(normalized(fact)) + '|' + KOREAN_FACTS.get(fact, r'(?!)')
    return bool(re.search(r'(?<![0-9a-z_])(?:' + alias + r')(?![0-9a-z_])', prose))

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
        korean = bool(re.search(r'[가-힣]', prose))
        # Connective endings delimit a following clause; commas in numeric lists stay intact.
        ko_assertions = [clause for assertion in assertions for clause in re.split(r'(?<=며),?\s+|(?<=하고),?\s+|(?<=비우고),?\s+', assertion)]
        english_assertions = [assertion for assertion in assertions if not re.search(r'[가-힣]', assertion)]
        relations = zip(CLAIMS[heading], CLAIMS_KO[heading])
        if not all(affirmative_claim(english_assertions,claim) or korean_claim(ko_assertions,claim) or korean_claim(ko_assertions,ko_claim) for claim,ko_claim in relations):
            return False, 'missing affirmative relation: ' + heading
        implicit_option = {'Kafka rejected':'Kafka', 'Redis rejected':'Redis Streams'}.get(heading) if korean else None
        if not all(f == implicit_option or evidence(f, prose, korean) for f in facts):
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
