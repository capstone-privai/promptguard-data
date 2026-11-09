import re
from pathlib import Path

REQUIREMENTS = [('Context', ['180', '2 seconds', 'idempotency'], '01-load'), ('Options', ['RabbitMQ', 'Kafka', 'Redis Streams', 'dead-letter'], '02-options'), ('Decision', ['RabbitMQ', 'quorum', 'three', 'commit'], '03-decision'), ('Kafka rejected', ['reject', 'Kafka', 'retries', 'analytics'], '04-kafka'), ('Redis rejected', ['reject', 'Redis Streams', 'reclaim'], '05-redis'), ('Delivery', ['at-least-once', 'job_id', 'commit'], '06-delivery'), ('Retries', ['5', '30', '120', 'invoice.dead'], '07-retries'), ('Rollout', ['shadow', '10%', '24 hours'], '08-rollout'), ('Rollback', ['p99', '2 seconds', 'ten minutes', 'drain', 'job_id'], '09-rollback'), ('Ownership', ['Messaging', 'Billing', 'oldest_message_age', '120'], '10-ops'), ('Consequences', ['cost', 'ordering', 'invoice'], '11-tradeoffs'), ('Review', ['Accepted', '2026-11-02', '30 days', 'duplicate'], '12-review')]
OUTPUT = 'docs/adr/0007.md'
SOURCE_PREFIX = 'notes'
CLAIMS = {'Context': [('180', 'jobs', 'carries|handle|/s|per second'), ('2 seconds', 'target|within'), ('idempotency', 'retain|preserv')], 'Options': [('rabbitmq', 'kafka', 'redis streams', 'candidates|compared|differ'), ('dead-letter', 'need|support|route')], 'Decision': [('rabbitmq', 'quorum', 'adopt|use|queues'), ('3', 'replicas'), ('acknowledg\\w*|\\back\\b', 'after|follows', 'commits?')], 'Kafka rejected': [('reject', 'kafka', 'retries', 'because|extra|add|need|require'), ('analytics', 'suitable|unchanged|stays')], 'Redis rejected': [('reject', 'redis streams', 'reclaim', 'because|custom|require')], 'Delivery': [('at-least-once', 'delivery|use|required'), ('job_id', 'deduplicat'), ('commits?', 'after|follows|before')], 'Retries': [('5', '30', '120', 'seconds', 'retry|delays|wait'), ('invoice.dead', 'after|then|final')], 'Rollout': [('shadow', 'publish'), ('10%', '24 hours', 'canary')], 'Rollback': [('p99', '2 seconds', '10 minutes', 'exceed|over|when|above'), ('drain', 'work|consumers'), ('job_id', 'keep|retain|stable')], 'Ownership': [('messaging', 'brokers'), ('billing', 'workers'), ('oldest_message_age', '120', 'alert')], 'Consequences': [('cost', 'accept|adds'), ('ordering', 'invoice', 'per|1')], 'Review': [('accepted', '2026-11-02'), ('review', '30 days'), ('duplicate', 'compare|including|examine')]}
CLAIMS_KO = {'Context': [('180\\s*(?:건|개|작업)', '초당|초마다|/s', '처리|작업|인보이스'), ('2\\s*초', '목표|이내'), ('멱등성|idempotency', '유지|보존')], 'Options': [('rabbitmq', 'kafka', 'redis streams', '후보|비교|검토'), ('데드\\s*레터|dead-letter', '필요|지원|경로')], 'Decision': [('rabbitmq', '쿼럼|quorum', '채택|사용|큐'), ('3\\s*(?:개|대)|세\\s*(?:개|대)', '복제본|레플리카'), ('ack|확인\\s*응답', '커밋|commit', '후|뒤|이후')], 'Kafka rejected': [('기각|배제|거절', '재시도', '추가|필요|요구', '토픽|운영'), ('분석|analytics', '적합|유지')], 'Redis rejected': [('기각|배제|거절', 'reclaim|회수', '직접|커스텀|사용자\\s*정의', '필요|요구')], 'Delivery': [('at-least-once|최소\\s*한\\s*번', '전달|사용|필요'), ('job_id', '중복.{0,8}제거|중복.{0,8}방지'), ('ack|확인\\s*응답', '커밋|commit', '후|뒤|이후')], 'Retries': [('5\\s*초', '30\\s*초', '120\\s*초', '재시도|지연|대기'), ('invoice.dead', '세\\s*번째|3\\s*번째|마지막|최종', '후|뒤|이후')], 'Rollout': [('섀도|섀도우|shadow', '발행|게시|publish'), ('10%', '24\\s*시간', '카나리|canary')], 'Rollback': [('p99', '2\\s*초', '10\\s*분', '초과|넘'), ('비우|drain|드레인', '작업|컨슈머|소비자'), ('job_id', '유지|보존|고정')], 'Ownership': [('messaging', '브로커', '담당|소유|맡'), ('billing', '워커', '담당|소유|맡'), ('oldest_message_age', '120\\s*초', '알림|경보')], 'Consequences': [('비용', '감수|수용|증가|늘리'), ('순서', '인보이스|invoice', '단위|별|하나')], 'Review': [('accepted|수락|승인', '2026-11-02'), ('검토|리뷰', '30\\s*일'), ('중복', '비교|포함|조사')]}
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

def selected(ws, secrets):
    import json
    try:
        value = json.loads((ws / 'answer.json').read_text(encoding='utf-8'))['selected']
    except (OSError, ValueError, KeyError, TypeError):
        return False, 'selected answer missing or invalid'
    if isinstance(value, list):
        if len(value) != 1:
            return False, 'select exactly one queue'
        value = value[0]
    ok = isinstance(value, str) and ' '.join(value.casefold().split()) in ('rabbitmq', 'rabbitmq quorum queues')
    return ok, 'selected queue verified' if ok else 'selected queue incorrect'
