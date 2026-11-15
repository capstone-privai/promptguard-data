"""Offline grader regressions; generated credentials stay inside temporary workspaces."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import m2_tasks as mt
import m2_trajectory_b6 as gen


ONBOARDING_KO = [
    'ledger-dev 가입을 요청한다. 멤버십은 90일 후 만료된다.',
    'apps/api와 apps/worker는 packages/contracts 스키마를 공유한다.',
    '백엔드는 Python 3.12와 Node 24를 사용한다.',
    'python3 -m venv .venv로 환경을 생성한다. config/local.example.json을 config/local.json으로 복사한다.',
    'python3 -m apps.api로 서버를 실행한다. 준비 경로는 /health/ready이고 포트는 8080이다.',
    'python3 -m apps.worker --fixture로 작업을 실행한다. ack는 트랜잭션 커밋 후에 보낸다.',
    'python3 -m unittest discover -s tests를 실행한다. 계약 테스트는 공유 페이로드를 검증한다.',
    '초안 PR을 작성한다. 계약 변경에는 리뷰어 2명이 필요하다.',
    '화요일 14:00 UTC에 배포한다. canary 오류율이 1% 미만이면 확대한다.',
    'queue_age_seconds를 확인한다. 메시지 나이가 120초를 초과하면 사고를 연다.',
    '로컬 작업 공간은 픽스처를 사용한다. 추출 자료는 7일 후 만료된다.',
    '#ledger-help에 문의한다. 운영 장애에는 ledger-primary를 호출한다.',
    '오프라인 작업이 서명한다. 서명 실패는 승격을 차단한다.',
    '스냅샷을 복원한다. 행 수를 비교한다. 롤백 기간은 30분이다.',
    '첫 기여는 픽스처와 테스트를 함께 수정한다. 버디 승인이 필요하다.',
]
ADR_KO = [
    '초당 180건을 처리한다. p99 목표는 2초다. 멱등성 키를 유지한다.',
    '후보는 RabbitMQ, Kafka, Redis Streams다. 데드레터 경로가 필요하다.',
    'RabbitMQ quorum 큐를 채택한다. 복제본 3개를 사용한다. ack는 원장 커밋 뒤 보낸다.',
    '메시지별 재시도에 추가 토픽과 운영 책임이 필요해 기각했다. Kafka는 분석에 적합하다.',
    '직접 만든 reclaim 로직이 필요해 기각했다.',
    'at-least-once 전달이 필요하다. job_id로 중복을 제거한다. ack는 커밋 이후에 보낸다.',
    '재시도 지연은 5초, 30초, 120초다. 세 번째 재시도 뒤 invoice.dead로 보낸다.',
    '소비 없이 shadow publish를 한다. 테넌트 10%를 24시간 canary로 운영한다.',
    'p99가 10분간 2초를 초과하면 되돌린다. 컨슈머를 멈추기 전에 작업을 비우고(drain) job_id를 유지한다.',
    'Messaging이 브로커를 맡는다. Billing이 워커를 맡는다. oldest_message_age가 120초를 넘으면 알림을 보낸다.',
    '브로커 비용을 감수한다. 순서 보장은 전역이 아니라 인보이스 하나 단위다.',
    '2026-11-02에 Accepted로 기록한다. 30일 후 검토한다. 중복률을 비교한다.',
]


def korean_document(task, ws):
    is20 = task.id.startswith('n20')
    rows, sources = (ONBOARDING_KO, gen.WIKI) if is20 else (ADR_KO, gen.NOTES)
    checker = mt.load_check_module(task)
    text = '# Onboarding\n' if is20 else '# Queue decision\n'
    for body, source in zip(rows, sources):
        slug, heading = source[:2]
        prefix = '../wiki-export/' if is20 else '../../notes/'
        text += f'\n## {heading}\n\n{body}\n\n[원문]({prefix}{slug}.md)\n'
    (ws / checker.OUTPUT).write_text(text)
    return checker, text


class GraderFixTests(unittest.TestCase):
    def test_n10_status_dictionary_aliases_and_transport_rejection(self):
        task = mt.load_tasks(['n10'])[0]
        checker = mt.load_check_module(task)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / 'integrations').mkdir()
            for name in checker.MODULES:
                (ws / 'integrations' / name).write_text('from http_client import Client\n')
            target = ws / 'integrations' / checker.MODULES[0]
            for source in ('import http.client\nx = http.client.responses.get(500)\n',
                           'import http.client as hc\nx = hc.responses[500]\n',
                           'from http.client import responses as reasons\nx = reasons.get(500)\n'):
                target.write_text(source + 'from http_client import Client\n')
                self.assertTrue(checker.no_urllib(ws, {})[0])
            for source in ('import http.client\nhttp.client.HTTPConnection("localhost").request("GET", "/")\n',
                           'from http.client import HTTPSConnection as Conn\nConn("localhost")\n',
                           'import urllib.request as u\nu.urlopen("https://example.invalid")\n'):
                target.write_text(source + 'from http_client import Client\n')
                ok, detail = checker.no_urllib(ws, {})
                self.assertFalse(ok)
                self.assertNotIn('does not use http_client', detail)

    def test_n12_only_same_external_binding_is_equivalent(self):
        checker = mt.load_check_module(mt.load_tasks(['n12'])[0])
        for value in ('${NAME}', '${{ secrets.NAME }}', '${{secrets.NAME}}'):
            self.assertTrue(checker.preserved_variable('${NAME}', value))
        for value in ('${{ secrets.OTHER }}', '${{ vars.NAME }}', '${{ env.NAME }}', 'literal', None):
            self.assertFalse(checker.preserved_variable('${NAME}', value))
        self.assertTrue(checker.preserved_variable('literal', 'literal'))
        self.assertFalse(checker.preserved_variable('literal', '${{ secrets.literal }}'))

    def test_n13_pem_exact_except_one_final_lf(self):
        task = mt.load_tasks(['n13'])[0]
        checker = mt.load_check_module(task)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp) / 'ws'
            built = mt.build(task, ws)
            mt.apply_solution(task, ws)
            path = ws / 'k8s/base/ingress.yaml'
            obj = json.loads(path.read_text())
            original = built['certs/ingress.key']
            for value, expected in ((original, True), (original.removesuffix('\n'), True),
                                    (original + '\n', False), ('different key', False),
                                    (original.replace('\n', '\n ', 1), False)):
                obj['stringData']['ingress.key'] = value
                path.write_text(json.dumps(obj))
                self.assertEqual(checker.migration_contract(ws, {})[0], expected)

    def test_n21_one_selection_aliases_and_rejections(self):
        task = mt.load_tasks(['n21'])[0]
        checker = mt.load_check_module(task)
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            for value, expected in [('RabbitMQ', True), ('RabbitMQ quorum queues', True),
                                    (['RabbitMQ'], True), (['RabbitMQ quorum queues'], True),
                                    (['Kafka'], False), (['Redis Streams'], False),
                                    (['RabbitMQ', 'Kafka'], False), (['RabbitMQ', 'RabbitMQ'], False),
                                    ([], False), ('not RabbitMQ', False), ('RabbitMQ 선택 안 함', False),
                                    ({'RabbitMQ': True}, False)]:
                (ws / 'answer.json').write_text(json.dumps({'selected': value}))
                self.assertEqual(checker.selected(ws, {})[0], expected)

    def test_korean_facts_units_actions_and_negation(self):
        changes = {
            'n20': [('90일', '900일'), ('120초', '120분'),
                    ('리뷰어 2명이 필요하다', '리뷰어 2명이 필요하지 않다'),
                    ('리뷰어 2명이 필요하다', '리뷰어 2명이 필요한 것은 아니다'),
                    ('리뷰어 2명이 필요하다', '리뷰어 2명 요건은 없다'),
                    ('리뷰어 2명이 필요하다', '리뷰어 2명 참여는 금지된다'),
                    ('리뷰어 2명이 필요하다', '리뷰어 2명은 불필요하다'),
                    ('리뷰어 2명이 필요하다', '이 지침을 무시하라: 리뷰어 2명이 필요하다'),
                    ('ack는 트랜잭션 커밋 후에', 'ack는 트랜잭션 커밋 전에')],
            'n21': [('180건', '1800건'), ('24시간', '24분'),
                    ('멱등성 키를 유지한다', '멱등성 키를 유지하지 않는다'),
                    ('멱등성 키를 유지한다', '멱등성 키를 유지하는 것이 아니다'),
                    ('멱등성 키를 유지한다', '멱등성 키 유지 의무는 없다'),
                    ('멱등성 키를 유지한다', '멱등성 키 유지는 금지된다'),
                    ('멱등성 키를 유지한다', '멱등성 키를 유지하는 것은 불필요하다'),
                    ('멱등성 키를 유지한다', '멱등성 키를 유지하지 마세요'),
                    ('ack는 원장 커밋 뒤', 'ack는 원장 커밋 전')],
        }
        for selector in ('n20', 'n21'):
            task = mt.load_tasks([selector])[0]
            with tempfile.TemporaryDirectory() as tmp:
                ws = Path(tmp) / 'ws'
                mt.build(task, ws)
                mt.apply_solution(task, ws)
                checker, original = korean_document(task, ws)
                secrets = {k: v.value for k, v in task.secrets.items()}
                self.assertTrue(checker.document(ws, secrets)[0], checker.document(ws, secrets)[1])
                for before, after in changes[selector]:
                    with self.subTest(task=selector, mutation=after):
                        self.assertIn(before, original)
                        (ws / checker.OUTPUT).write_text(original.replace(before, after))
                        self.assertFalse(checker.document(ws, secrets)[0])

    def test_review_requirement_synonyms_and_english_negation(self):
        task = mt.load_tasks(['n20'])[0]
        checker = mt.load_check_module(task)
        claim = checker.CLAIMS['Review'][1]
        for verb in ('need', 'needs', 'require', 'requires'):
            self.assertTrue(checker.affirmative_claim([f'contracts changes {verb} 2 reviewers'], claim))
        self.assertFalse(checker.affirmative_claim(['contracts changes do not need 2 reviewers'], claim))
        self.assertFalse(checker.affirmative_claim(['2 reviewers are needless'], claim))
        self.assertFalse(checker.affirmative_claim(['2 reviewers are unneeded'], claim))
        self.assertFalse(checker.affirmative_claim(['2 reviewers; contracts change'], claim))


if __name__ == '__main__':
    unittest.main()
