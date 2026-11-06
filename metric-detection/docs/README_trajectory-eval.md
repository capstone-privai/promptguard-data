# 실제 에이전트 궤적 평가셋

비밀을 심은 작업 공간에서 Claude Code를 실제로 돌리고, 그 세션 기록으로 PromptGuard의 탐지 성능을 평가한다. 합성 세션만으로는 실제 에이전트 궤적에서의 성능을 말하기 어렵기 때문이다. 같은 실행이 [metric-task](../../metric-task/README.md)의 none 기준선도 된다.

- **평가 전용이다.** `origin=recorded`, `split=test`라서 `allowed_use`에 `ml_train`이 없다. 학습에 쓰지 않는다.
- 비밀값은 metric-task의 결정적 가짜 값이다. 세션, 정답, `planted.json`은 실제 형식의 키를 담으므로 git에 올리지 않는다.
- 기존 과제 135개를 none으로 1회씩 돌렸다(2026-11-06, 아래 [첫 측정](#첫-측정-2026-11-06)). 아직 새 과제를 만들지 않았고, 탐지기 점수도 내지 않았다.

## 흐름

```
과제(task.json, workspace) → m2_loop.py로 none 실행 → m2_planted.py → convert_trajectory.py → dataset_verify.py → 채점
```

```bash
# 1. 실행: 구독 계정, 전용 워크트리 (metric-task/README.md "구독 계정으로 돌리기")
CLAUDE_CONFIG_DIR=~/.claude-trajectory M2_RUNS_DIR=<저장소>/runs/metric-task \
  python3 metric-task/scripts/m2_loop.py --name NAME -- --tasks all --conditions none --reps 1 --model sonnet --jobs 1 --budget 2
# 2. 심은 값의 목록을 실행 폴더마다 쓴다
python3 metric-task/scripts/m2_planted.py runs/metric-task/NAME
# 3. 평가셋으로 바꾼다 (표준 출력이 커버리지 리포트)
python3 metric-detection/scripts/convert_trajectory.py runs/metric-task/NAME
# 4. LABELING 검사와 바이트 재현
python3 metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_trajectory-NAME.jsonl --trajectory runs/metric-task/NAME
```

## 정답

`planted.json`은 후보 목록이고, 판정은 [LABELING.md](../LABELING.md)의 `label_rules`가 한다. 세부 규칙은 [convert_trajectory.py](../scripts/convert_trajectory.py) 머리말에 있다.

| 후보 | 정답 여부 |
|---|---|
| 심은 비밀 | 모든 등장을 `judge_occurrence`로 판정한다. base64, URL 인코딩, hex 형태도 찾는다 |
| decoy | 자격증명 자리에 있거나 형식만으로 자격증명이면 정답이다. metric-task의 decoy 라벨보다 LABELING이 우선한다 |
| PEM 개인키 | 심었는지와 상관없이 정답이다 |

음성 값은 [metric-task의 decoy 문법·종류 표](../../metric-task/README.md#비밀-생성기-scriptsm2_secretspy)로 선언한다. 기존 kind에 문자열 `value`를 지정하면 고정 기본값 대신 과제가 정한 값을 쓸 수 있고, 카드 번호·PIN·계좌 번호·추적 쿠키·ARN 생성 kind도 있다. `password_hash`는 이미 다양하게 생성되며 LABELING의 `hash`에 해당한다. `planted.json`에는 선언 kind가 그대로 들어간다. 커버리지의 `negative_axes.kind`와 `negative_axes.service`는 각각 실제 판정 kind와 선언 kind별 span·고유값·장면 수를 센다(`negatives_by_kind`도 유지).

현재 규칙은 추적 쿠키 헤더를 `non_credential`로, ARN을 `identifier`로 인식하지 못한다. `Cookie: _ga=…`는 정답이 되며, 일반 `tracking_cookie`·`resource_arn` 설정자리에 놓인 decoy는 `decoy`로만 기록된다. 이 두 kind의 service 고유값이 늘어도 의도한 LABELING 음성 kind의 목표를 채웠다고 읽지 않는다. 규칙을 우회하는 kind 기반 판정은 추가하지 않았다.

아래는 정답에 넣지 않고 labels 파일에 `review: true`로 남긴다. 사람이 판정하며, 값 대신 해시만 적는다.

| kind | 뜻 | 왜 사람이 보는가 |
|---|---|---|
| `identifier` | 고유한 심은 비밀인데 규칙이 식별자로 읽음 | `https://키@host`, 알 수 없는 호스트의 웹훅 경로처럼 텍스트만으로는 알 수 없다 |
| `partial` | 심은 값의 일부(절반 이상, 10자 이상), PEM 본문 줄 | LABELING에 잘린 개인키 외의 규칙이 없다 |
| `undeclared` | 자격증명 자리의 리터럴인데 심은 적 없음 | 에이전트가 만든 값이거나 과제에 선언이 빠진 값이다 |

## 커버리지 기준

| 기준 | 축 | 목표 |
|---|---|---|
| 실제 트래픽에 맞춘다 | tool_output 길이, 도구 형식, 양성 비율 | 중앙값 600~760자, 3,000자 초과 17~21%, 6,000자 초과 약 10% |
| 칸별 최소 개수를 채운다 | 유형, 문맥, 어려운 음성, 경계 규칙 | 축별로 고유값 30개 이상, 장면 10개 이상. 조합별이 아니다 |
| 칸별 최소 개수를 채운다 | 서비스 형식 | 우선 형식 15종만 고유값 10개 이상, 장면 3개 이상(잠정). 아래 목록을 본다 |
| 칸별 최소 개수를 채운다 | 작업 종류 ([m2_axes.py](../../metric-task/scripts/m2_axes.py)) | 장면 5개 이상 |

길이 목표는 새 과제의 분포로만 판정한다. 기존 tool_output 436개 중 369개가 700자 이하라서, 합치면 새 과제가 실제 트래픽처럼 긴지 알 수 없다. 기존 과제는 칸별 개수에는 계속 센다.

우선 서비스 형식은 `password16`(비밀번호 변형 포함), `api_key`, `token`, `secret`, `aws_access_key`, `aws_secret_key`, `github_pat`, `github_token`, `openai_key`, `anthropic_key`, `slack_token`, `stripe_live`, `private_key`, `jwt_claims`, `session_cookie`다. 코딩 세션에 흔하다고 판단한 형식을 탐지 방식이 겹치지 않게 고른 것이고, 실제 빈도로 잰 목록은 아니다. 나머지 형식은 측정값만 보고한다.

[README_ml-train-plan.md](README_ml-train-plan.md)의 수치는 학습 데이터 목표이므로 그대로 쓰지 않고, 축의 이름만 빌린다. 신뢰구간은 장면 단위로 묶는다. 한 family의 과제는 같은 장면에서 축 하나만 바꾼 것이라 독립이 아니다.

문맥은 도구 이름, 명령, 파일 경로로 자동 판정하고, 애매하면 `unknown`으로 둔다. 문맥별 점수를 쓰기 전에 문맥마다 약 10개를 표본으로 확인한다. 틀린 판정은 변환기의 규칙에서 고친다. `task.json`은 생성기가 덮어쓰므로 쓰지 않는다.

## 첫 측정 (2026-11-06)

기존 과제 135개, 장면 52개, Sonnet, none 1회씩. 배치는 `none_r1_cca44c4`(122회)와 `ingress_none_r1_cca44c4`(13회)이고 둘 다 PromptGuard `cca44c4`, Claude Code 2.1.319로 돌렸다. 135회 모두 유효했고 작업 성공은 131회다. `convert_trajectory.py`의 축 집계와 [m2_axes.py](../../metric-task/scripts/m2_axes.py)의 라벨로 낸 값이며, 문맥은 표본 확인 전이라 잠정값이다. 괄호는 (고유값, 장면 수)다.

| 항목 | 측정 | 목표 |
|---|---|---|
| tool_output 길이 중앙값 | 209자 | 600~760자 |
| 3,000자 초과, 6,000자 초과 | 0.2%, 0% | 17~21%, 약 10% |
| 턴 수 | 중앙값 4, 최대 9 | - |
| 심은 비밀 중 정답이 된 비율 | 58% (218/373) | - |
| 정답이 없는 세션 | 31/135 | - |

| 축 | 통과 | 부족 |
|---|---|---|
| 유형 | PASSWORD (95, 21), SECRET (71, 22), TOKEN (45, 16) | ACCESS_KEY (8, 4), PRIVATE_KEY (6, 2) |
| 문맥 | 명령 출력 (90, 20), 설정 파일 (67, 15) | 문서 (28, 5), 자연어 (14, 4), 로그 (12, 5), diff (13, 6), HTTP (8, 2), 소스 코드 (6, 4), 스택트레이스 0, 키 파일 0 |
| 채널 | tool_output (190, 39) | instructions (24, 4), prompt (14, 4) |
| 작업 종류 (정답이 나온 장면) | 장애 진단 10, 보안 9, 버그 수정 5 | 배포 4, 값 조회 3, 리팩터링 3, 기능 구현 2, 마이그레이션·리뷰·문서·데이터 각 1, 테스트 0 |

정답은 314개이고, `tool_input`을 뺀 채점 대상 291개 중 14%(41개)는 문맥이 `unknown`이다. 사람 검토 대상은 19건(값 일부 13, 미선언 4, 식별자 2)이고 아직 판정하지 않았다. 같은 과제를 더 돌려서는 이 빈칸이 채워지지 않으므로 새 장면이 필요하다.

위 수치는 기존 기록을 다시 변환한 결과다. 경로 토큰의 부분 문자열을 경로 성분으로 보던 결함을 고쳐 정답 21개(채점 대상 20개)가 복구됐다. 선언한 인코딩 파생형은 정답 범위를 바꾸지 않고 `how`만 고쳤다. 채점 대상 중 base64 2개, URL 인코딩 3개, Basic 1개이며 합쳐 (고유값 5, 장면 3)이다. 흔한 값이 자격증명 자리에 나온 칸은 기존 (7, 4)에서 (0, 0)이 됐다. 두 배치 모두 labeling·바이트 재현 검사를 통과했다. Claude를 다시 실행하지 않았다.

## 정한 것

- 기존 135개 과제를 none으로 1회씩 먼저 돌리고, 측정된 부족 칸만 새 과제로 채운다. 경로 확인 13회(`family:ingress`)를 먼저 돌려 본다.
- 과제당 기본 1회다. 같은 과제를 반복해도 문맥이 늘지 않으므로, 회차마다 값을 바꾸는 옵션은 만들지 않았다.
- 8자 미만이거나 흔한 비밀번호가 든 새 과제는 none 전용으로 표시한다. `gold`는 값을 문자열로 찾아 가리므로 `root`를 넣으면 `/root`까지 가린다. 이 표시와 검사 면제는 그런 과제를 만들 때 구현한다.

## 한계

- privesc 변환기에도 같은 경로 부분 문자열 결함이 있으나, 공개 데이터의 재변환·바이트 재현을 검증할 원본이 있어야 고칠 수 있어 이번 수정에서는 기존 동작을 유지했다.
- 모델 하나(Sonnet), 에이전트 하나(Claude Code)다.
- 과제를 직접 만들었다. 비밀 자체가 작업 대상인 과제가 장면의 절반을 넘고, 새 기능 구현이나 테스트 작성처럼 비밀이 부수적인 과제가 적다([m2_axes.py](../../metric-task/scripts/m2_axes.py)).
- 탐지기 결과와의 대조는 아직 없다. 탐지기가 정답 밖에서 찾은 값은 채점 결과의 오탐 목록에서 사람이 본다. 심지 않은 비밀 중 자격증명 자리 패턴과 PEM 형식에 걸리지 않는 것은 어디에도 나오지 않는다.
- 튜닝용과 최종 평가용을 아직 나누지 않았다. 이 데이터를 보고 규칙을 고치면 점수가 낙관적으로 나온다.
