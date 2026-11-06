# 실제 에이전트 궤적 평가셋

비밀을 심은 작업 공간에서 Claude Code를 실제로 돌리고, 그 세션 기록으로 PromptGuard의 탐지 성능을 평가한다. 합성 세션만으로는 실제 에이전트 궤적에서의 성능을 말하기 어렵기 때문이다. 같은 실행이 [metric-task](../../metric-task/README.md)의 none 기준선도 된다.

- **평가 전용이다.** `origin=recorded`, `split=test`라서 `allowed_use`에 `ml_train`이 없다. 학습에 쓰지 않는다.
- 비밀값은 metric-task의 결정적 가짜 값이다. 세션, 정답, `planted.json`은 실제 형식의 키를 담으므로 git에 올리지 않는다.
- 아직 새 배치를 돌리지 않았다. 변환기는 기존 `capture_trial` 배치(none 10회)로만 검증했다.

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
| 칸별 최소 개수를 채운다 | 유형, 서비스 형식, 문맥, 어려운 음성, 경계 규칙 | 축별로 고유값 30개 이상, 장면 10개 이상. 조합별이 아니다 |
| 칸별 최소 개수를 채운다 | 작업 종류 ([m2_axes.py](../../metric-task/scripts/m2_axes.py)) | 장면 5개 이상 |

[README_ml-train-plan.md](README_ml-train-plan.md)의 수치는 학습 데이터 목표이므로 그대로 쓰지 않고, 축의 이름만 빌린다. 신뢰구간은 장면 단위로 묶는다. 한 family의 과제는 같은 장면에서 축 하나만 바꾼 것이라 독립이 아니다.

문맥은 도구 이름, 명령, 파일 경로로 자동 판정하고, 애매하면 `unknown`으로 둔다. 문맥별 점수를 쓰기 전에 문맥마다 약 10개를 표본으로 확인한다. 틀린 판정은 변환기의 규칙에서 고친다. `task.json`은 생성기가 덮어쓰므로 쓰지 않는다.

## 정한 것

- 기존 135개 과제를 none으로 1회씩 먼저 돌리고, 측정된 부족 칸만 새 과제로 채운다. 경로 확인 13회(`family:ingress`)를 먼저 돌려 본다.
- 과제당 기본 1회다. 같은 과제를 반복해도 문맥이 늘지 않으므로, 회차마다 값을 바꾸는 옵션은 만들지 않았다.
- 8자 미만이거나 흔한 비밀번호가 든 새 과제는 none 전용으로 표시한다. `gold`는 값을 문자열로 찾아 가리므로 `root`를 넣으면 `/root`까지 가린다. 이 표시와 검사 면제는 그런 과제를 만들 때 구현한다.

## 한계

- 모델 하나(Sonnet), 에이전트 하나(Claude Code)다.
- 과제를 직접 만들었다. 비밀 자체가 작업 대상인 과제가 장면의 절반을 넘고, 새 기능 구현이나 테스트 작성처럼 비밀이 부수적인 과제가 적다([m2_axes.py](../../metric-task/scripts/m2_axes.py)).
- 탐지기 결과와의 대조는 아직 없다. 탐지기가 정답 밖에서 찾은 값은 채점 결과의 오탐 목록에서 사람이 본다. 심지 않은 비밀 중 자격증명 자리 패턴과 PEM 형식에 걸리지 않는 것은 어디에도 나오지 않는다.
- 튜닝용과 최종 평가용을 아직 나누지 않았다. 이 데이터를 보고 규칙을 고치면 점수가 낙관적으로 나온다.
