# 대시보드의 알려진 버그

2026-10-17 코드 리뷰에서 찾은 논리 오류 중 아직 고치지 않은 것이다. 이 문서만 보고 고칠 수 있게 항목마다 원인, 재현, 고칠 방향, 끝났다고 볼 기준을 적는다. 번호는 리뷰 때 번호를 그대로 쓴다. 이미 고친 것:

- 1번, 머지된 기능 브랜치 안의 커밋이 `main` 이력처럼 추이에 섞임: `repo.commits()`가 `--first-parent`를 쓴다.
- 2번, 표시 전용인 `catalog.py`의 데이터셋 순서가 벤치마크 지문에 들어감: 지문에는 데이터셋을 이름순으로 넣는다(`tests/test_runner.py`).
- 3번, 커밋을 연달아 고르면 다른 커밋의 숫자가 굳음: `loadResults()`가 마지막 호출의 응답만 반영하고, 그 호출만 화면을 다시 그린다.
- 4번, 요청이 한 번만 실패해도 실시간 갱신이 꺼지고 화면이 빔: `pollStatus()`는 4xx(API가 없는 정적 사본)일 때만 폴링을 끄고 네트워크 오류와 5xx는 다음 주기에 다시 묻는다. `refreshIndex()`는 받기에 실패하면 이전 index를 그대로 두고, index가 한 번도 없으면 다음 폴링 때 다시 받는다.
- 5번, 같은 데이터 폴더에서 평가가 둘 돌면 서로의 작업 폴더를 지움: Linux/macOS에서 `Service`가 `.lock`을 잡아 평가 프로세스를 하나로 제한한다. 잠금을 못 잡은 `--once`는 종료 코드 3으로 끝나고, 서버는 화면을 제공하며 기다린다. 평가 루프가 끝나면 잠금을 푼다(`tests/test_service.py`, `tests/test_serve.py`).

- 6번, 예시 창과 태그가 샤드 나눔에 따라 달라짐: 샤드가 후보의 초점과 원문을 넘기고, `merge()`가 전체 상위 후보를 고른 뒤 창을 자른다. 한 item이 일부 버킷에서만 밀리는 경우에도 샤드 수·순서와 무관하게 예시 전체가 같다(`tests/test_collect.py`).

- 7번, 지연 timeout 기준과 표시가 다름: 커밋의 `detectorTimeoutMs`를 측정 옵션과 지연 결과 키에 넣는다. timeout만 바꾸면 탐지 키는 그대로다. 헤드라인은 앙상블의 초과 횟수만 세고 화면은 측정값의 기준을 표시한다. `LATENCY_VERSION`은 2다(`tests/test_repo.py`, `tests/test_service.py`, `tests/test_latency.py`).

- 8번, 상위 경로에 `tests`가 있으면 채점 코드 지문이 고정됨: 테스트 파일 제외 여부를 저장소 내부 상대 경로로 판정한다. 채점기와 대시보드 집계 코드는 모두 지문에 들어가며, 일반 경로의 지문은 그대로다(`tests/test_runner.py`).

줄 번호는 작성 시점 기준이니 함수 이름으로 찾는다. 하나를 고치면 이 문서에서 그 항목을 지운다.

## 고치기 전에

- 작성 시점에 대시보드는 `detection-dashboard` 브랜치에만 있다. 그 브랜치에서 새 브랜치를 파서 작업한다. 이 저장소의 브랜치 이름은 `feature/` 같은 접두사 없는 kebab-case다. 커밋은 사용자가 요청할 때만 한다.
- 테스트: `python3 -m unittest discover -s dashboard/tests -t dashboard` (작성 시점 31개 통과). Python 쪽은 고치기 전에 실패하는 테스트부터 넣는다. 화면(`web/app.js`)은 테스트가 없으니 아래 재현으로 확인하고 `node --check dashboard/web/app.js`를 돌린다.
- 결과 키: `pipeline/taxonomy.py`, `collect.py`, `shard.py`, `metric-detection/evaluation/`을 바꾸면 탐지 결과 키가 바뀌어 모든 커밋을 다시 평가한다(탐지기 상태 하나에 8코어로 약 20분). `latency.py`의 `condense()`나 `latency.json` 형식을 바꾸면 `LATENCY_VERSION`을 올린다. 키가 바뀌는 것은 괜찮지만, 바뀐다는 것을 알고 고친다.
- 숫자 정의는 바꾸지 않는다. P/R/F1은 공식 채점기(`metric-detection/evaluation/report/aggregate.py`)와 같아야 하고, `collect.merge()`가 셀 합계를 채점기 개수와 대조한다.
- `runs/`는 git에 올리지 않는다. 결과에 데이터셋 원문과 비밀값이 든 예시가 있다. 로컬에는 실제 결과가 `runs/dashboard/`에 있어서 `python3 dashboard/serve.py --serve-only`로 http://127.0.0.1:8765 에서 화면을 볼 수 있다.
- metric-task는 API 비용이 들어서 대시보드가 돌리지 않는다. 실행 기능을 넣지 않는다.
- 결과 키, 샤드, 예시 고르기는 [README.md](README.md)의 "숫자는 이렇게 센다", "결과를 언제 다시 만드나"에 설명이 있다.

## 요약

| # | 심각도 | 어디 | 증상 |
|---|---|---|---|
| 9 | 낮음 | `app.js` `duration()` | 119.6초를 "1분 60초"로 보여 준다 |

## 9. duration()이 "1분 60초"를 만든다

- **어디**: [app.js](web/app.js) `duration()`(80행). 분은 `Math.floor(seconds / 60)`, 초는 `Math.round(seconds % 60)`로 따로 반올림한다.
- **증상**: 119.6초가 "1분 60초"가 된다. 위쪽 커밋 버튼 팝오버의 '탐지 평가' 소요 시간에 보인다.
- **고칠 방향**: 먼저 `Math.round(seconds)`로 반올림한 뒤 분과 초로 나눈다.

## 범위 밖 (여기서 고치지 않는다)

- **Precision이 수정 조각 수로 세진다**: 공식 채점기는 시스템이 가린 곳(수정)을 하나하나 센다. 928c84c에서 개인 키는 정답이 1,590개인데 '정답 안쪽 수정'은 9,721개다. PEM 키를 줄마다 따로 가리면 조각마다 맞은 수정으로 세지기 때문이다. 그래서 개인 키는 Precision 92.7%, Recall 10%이고, 전체 Precision에도 이 효과가 섞여 있다. 대시보드는 공식 정의를 따라야 하므로 여기서 바꾸지 않는다. 바꾸려면 metric-detection 채점기에서 정한다.
- **metric-task 배치가 체크아웃의 수정 여부를 남기지 않는다**: `metric-task/scripts/m2.py`는 `batch.json`의 `system_commit`에 `git rev-parse HEAD`만 적는다. 그래서 커밋하지 않은 수정이 있는 상태로 돌린 배치도 그 커밋의 결과로 붙는다. 고치려면 m2.py가 수정 여부를 기록하고, 대시보드가 그 표시를 보여 준다.

## 선택: 리뷰 중 본 작은 것

- `runner.validate()`의 캐시 키가 데이터셋 해시뿐이다. 채점기의 검증 규칙(`metric-detection/evaluation/dataset/validate.py`)이나 `shard.USE`가 바뀌어도 예전 검증 결과를 쓴다.
- 아직 진행 중인 metric-task 배치는 `runs.csv`가 늘 때마다 `task.batch_key()`가 바뀐다. 그래서 `results/task/`에 `task.json`이 주기마다 새로 쌓이고 지워지지 않는다.
- `POST /api/refresh`는 Basic 인증만 확인해서, 인증된 브라우저로 다른 사이트가 이 요청을 보내게 할 수 있다(CSRF). 하는 일이 다시 확인과 재시도뿐이라 피해는 작다.
