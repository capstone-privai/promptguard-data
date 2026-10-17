# 대시보드의 알려진 버그

2026-10-17 코드 리뷰에서 찾은 논리 오류 중 아직 고치지 않은 것이다. 이 문서만 보고 고칠 수 있게 항목마다 원인, 재현, 고칠 방향, 끝났다고 볼 기준을 적는다. 번호는 리뷰 때 번호를 그대로 쓴다. 1번(머지된 기능 브랜치 안의 커밋이 `main` 이력처럼 추이에 섞이던 문제)은 `repo.commits()`가 `--first-parent`를 쓰도록 고쳤다.

줄 번호는 작성 시점 기준이니 함수 이름으로 찾는다. 하나를 고치면 이 문서에서 그 항목을 지운다.

## 고치기 전에

- 작성 시점에 대시보드는 `detection-dashboard` 브랜치에만 있다. 그 브랜치에서 새 브랜치를 파서 작업한다. 이 저장소의 브랜치 이름은 `feature/` 같은 접두사 없는 kebab-case다. 커밋은 사용자가 요청할 때만 한다.
- 테스트: `python3 -m unittest discover -s dashboard/tests -t dashboard` (작성 시점 29개 통과). Python 쪽은 고치기 전에 실패하는 테스트부터 넣는다. 화면(`web/app.js`)은 테스트가 없으니 아래 재현으로 확인하고 `node --check dashboard/web/app.js`를 돌린다.
- 결과 키: `pipeline/taxonomy.py`, `collect.py`, `shard.py`, `metric-detection/evaluation/`을 바꾸면 탐지 결과 키가 바뀌어 모든 커밋을 다시 평가한다(탐지기 상태 하나에 8코어로 약 20분). `latency.py`의 `condense()`나 `latency.json` 형식을 바꾸면 `LATENCY_VERSION`을 올린다. 키가 바뀌는 것은 괜찮지만, 바뀐다는 것을 알고 고친다.
- 숫자 정의는 바꾸지 않는다. P/R/F1은 공식 채점기(`metric-detection/evaluation/report/aggregate.py`)와 같아야 하고, `collect.merge()`가 셀 합계를 채점기 개수와 대조한다.
- `runs/`는 git에 올리지 않는다. 결과에 데이터셋 원문과 비밀값이 든 예시가 있다. 로컬에는 실제 결과가 `runs/dashboard/`에 있어서 `python3 dashboard/serve.py --serve-only`로 http://127.0.0.1:8765 에서 화면을 볼 수 있다.
- metric-task는 API 비용이 들어서 대시보드가 돌리지 않는다. 실행 기능을 넣지 않는다.
- 결과 키, 샤드, 예시 고르기는 [README.md](README.md)의 "숫자는 이렇게 센다", "결과를 언제 다시 만드나"에 설명이 있다.

## 요약

| # | 심각도 | 어디 | 증상 |
|---|---|---|---|
| 2 | 중간 | `runner.py` `discover()`, `benchmark()` | 표시 전용인 `catalog.py`에서 데이터셋 순서만 바꿔도 모든 커밋을 다시 평가한다 |
| 3 | 중간 | `app.js` `loadResults()` | 커밋을 연달아 고르면 다른 커밋의 숫자가 나오고 그대로 굳는다 |
| 4 | 중간 | `app.js` `pollStatus()`, `refreshIndex()` | 요청이 한 번만 실패해도 실시간 갱신이 영영 꺼지고, 화면이 빈다 |
| 5 | 중간 | `runner.py` `evaluate()`, `service.py` `run_job()` | 같은 데이터 폴더에서 평가가 둘 돌면 서로의 작업 폴더를 지운다 |
| 6 | 낮음 | `collect.py` `Collector.payload()`, `merge()` | 예시 창과 태그가 샤드 나눔(`--jobs`)에 따라 달라진다 |
| 7 | 낮음 | `latency.py` `evaluate()`, `headline()` | timeout을 "시스템 값"이라고 보여 주지만 5000ms 고정이고, 헤드라인 `over_timeout`의 기준이 패널과 다르다 |
| 8 | 낮음 | `runner.py` `code_fingerprint()` | 저장소 경로에 `tests` 폴더가 끼면 채점 코드 지문이 고정된다 |
| 9 | 낮음 | `app.js` `duration()` | 119.6초를 "1분 60초"로 보여 준다 |

## 2. catalog.py의 데이터셋 순서가 벤치마크 지문에 들어간다

- **어디**: [runner.py](pipeline/runner.py) `discover()`(75행)가 `catalog.dataset_order()` 순서로 데이터셋을 돌려주고, `benchmark()`(98행)가 그 목록을 순서째 지문에 넣는다. `json.dumps(..., sort_keys=True)`는 딕셔너리 키만 정렬하고 리스트 순서는 그대로 둔다.
- **증상**: `catalog.py`는 "표시 전용이라 고쳐도 다시 평가하지 않는다"(catalog.py 문서 문자열, README의 파일 목록)고 했는데, `DATASETS`의 순서를 바꾸면 벤치마크 지문이 바뀐다. 모든 커밋이 다시 평가 대상이 되고, 다시 돌 때까지 화면은 '이전 기준' 결과를 보여 준다.
- **재현** (저장소 루트에서):
  ```python
  import sys
  sys.path.insert(0, "dashboard")
  from pipeline import catalog, runner
  from pipeline.paths import DATA_TEST
  before = runner.benchmark(runner.discover(DATA_TEST))["fingerprint"]
  items = list(catalog.DATASETS.items())
  items[0], items[1] = items[1], items[0]
  catalog.DATASETS.clear()
  catalog.DATASETS.update(items)
  after = runner.benchmark(runner.discover(DATA_TEST))["fingerprint"]
  print(before != after)  # 작성 시점에는 True (버그)
  ```
- **고칠 방향**: 지문에 넣을 때만 데이터셋을 이름(stem)순으로 정렬한다. 화면 순서는 지금처럼 `dataset_order()`를 따른다.
- **주의**: 정렬 방식이 바뀌니 고친 직후 한 번은 지문 값이 달라져 모든 커밋을 다시 평가한다. 서버에 올리기 전에 고치면 상관없다.
- **끝 기준**: 위 재현이 `False`를 내고, 이것을 테스트로 남긴다. 데이터셋 파일 내용이 바뀌면 지문이 바뀌는 것도 같이 확인한다.

## 3. 커밋을 연달아 고르면 다른 커밋의 숫자가 나오고 굳는다

- **어디**: [app.js](web/app.js) `loadResults()`(1327행). 요약을 받으면 `.then`에서 `state.summaryKey = state.detection.key`(1333행)로 저장한다. 받아 온 키가 아니라 그 순간 선택된 키다. `selectCommit()`과, 15초마다 도는 `pollStatus()` → `refreshIndex()`가 겹쳐 불려도 막는 장치가 없다.
- **증상**: 커밋 A를 누르고 응답이 오기 전에 B를 누르면, 늦게 온 A의 요약이 B의 키로 저장된다. 화면은 B(위쪽 커밋 버튼, 추이의 선택 표시)인데 숫자는 A다. 이후 `loadResults()`는 키가 같다고 보고 다시 받지 않아서 그대로 굳는다. 지연 패널(1342행)은 키를 맞게 저장하지만, 늦게 온 응답이 화면을 덮어쓰는 것은 같다.
- **재현** (node 18 이상, 저장소 루트에서 `node race.mjs`): `loadResults()`를 app.js에서 그대로 잘라 와 가짜 `getJSON`으로 돌린다.
  ```js
  // race.mjs: 커밋 A의 응답은 늦게(80ms), B는 빨리(10ms) 온다.
  import { readFileSync } from "node:fs";
  const source = readFileSync(process.argv[2] || "dashboard/web/app.js", "utf8");
  const body = source.slice(source.indexOf("async function loadResults()"), source.indexOf("/** Names and descriptions"));
  const delays = { A: 80, B: 10 };
  const state = { summary: null, summaryKey: null, latency: null, latencyKey: null, detection: null };
  let selected = "A";
  const pick = () => ({ key: selected });
  const tracks = () => [];
  const loadTask = async () => {};
  const getJSON = (url) => {
    const key = url.split("/")[3]; // data/results/detection/<key>/summary.json
    return new Promise((resolve) => setTimeout(() => resolve({ fetched: key }), delays[key]));
  };
  const loadResults = new Function("state", "pick", "tracks", "loadTask", "getJSON", `${body}; return loadResults;`)(
    state, pick, tracks, loadTask, getJSON);
  const first = loadResults(); // A를 누름
  selected = "B";
  const second = loadResults(); // A의 응답 전에 B를 누름
  await Promise.all([first, second]);
  console.log("selected:", selected, "| summary shown:", state.summary.fetched, "| summaryKey:", state.summaryKey);
  await loadResults(); // 그 뒤 아무 때나 다시 불러옴
  console.log("after reload -> summary shown:", state.summary.fetched, "| summaryKey:", state.summaryKey);
  ```
  작성 시점 출력: `selected: B | summary shown: A | summaryKey: B`, 다시 불러온 뒤에도 같다.
- **고칠 방향**: 요청할 때의 키를 붙잡아 두고, 응답이 왔을 때 그 키가 아직 선택돼 있을 때만 반영한다. `selectCommit()`과 `refreshIndex()`에는 순번을 두어 마지막 호출만 `renderAll()` 하게 한다. 지연(`latencyKey`)과 작업 성공(`loadTask()`)도 같은 방식으로 맞춘다. 고친 뒤에는 위 스크립트가 잘라 오는 범위(함수 이름, 다음 주석)가 바뀌지 않았는지 보고 돌린다.
- **끝 기준**: 위 재현이 `summary shown: B`를 내고, A의 응답이 나중에 와도 B가 유지된다.

## 4. 요청이 한 번만 실패해도 실시간 갱신이 꺼지고 화면이 빈다

- **어디**: [app.js](web/app.js) `pollStatus()`(1393행)의 `catch`는 무엇이 실패하든 `state.statusPolling = false`(1402행)로 폴링을 영구히 끈다. 원래 의도는 "API가 없는 정적 사본(`--export`)이면 끈다"였다. `refreshIndex()`(1383행)는 `index.json`을 못 받으면 `state.index = null`(1387행)로 비워서 화면 전체가 빈다.
- **증상**: 서버 재시작, 와이파이 끊김, 노트북 절전 해제 때 한 번만 실패해도, 열어 둔 탭은 새로 고칠 때까지 갱신되지 않는다. 서비스는 코드가 바뀌면 스스로 종료 코드 75로 끝나고 systemd가 다시 띄우므로, 서버 재시작은 드물지 않다. `index.json`을 한 번 못 받으면 멀쩡하던 화면이 비고, 다음 `index_at` 변경까지 그대로다.
- **재현**: `python3 dashboard/serve.py --serve-only`로 띄워 화면을 연다. 서버를 끄고 20초 기다린 뒤 다시 띄운다. 개발자 도구 콘솔에서 `state.statusPolling`이 `false`다.
- **고칠 방향**: 404(정적 사본)일 때만 폴링을 끄고, 네트워크 오류나 5xx는 다음 주기에 다시 시도한다(필요하면 간격을 점점 늘린다). `getJSON()`이 던지는 에러에 HTTP 상태를 붙이면 구분할 수 있다. `refreshIndex()`는 실패하면 이전 `state.index`를 그대로 둔다.
- **끝 기준**: 서버를 껐다 켜면 다음 폴링부터 다시 갱신된다. `--export`로 만든 정적 사본에서는 첫 404 뒤로 `/api/status`를 다시 요청하지 않는다.

## 5. 같은 데이터 폴더에서 평가가 둘 돌면 서로의 작업 폴더를 지운다

- **어디**: 데이터 폴더 잠금이 없다. [runner.py](pipeline/runner.py) `evaluate()`는 시작할 때 `results/detection/<키>.work`를 지우고(237–238행), `<키>.tmp`에 결과를 만든다(259행). [service.py](pipeline/service.py) `run_job()`은 커밋을 `checkouts/<지문 12자>`에 꺼내고(221행) 끝나면 지운다(252행). `failures.json`과 `index.json`도 프로세스마다 따로 덮어쓴다.
- **증상**: systemd 서비스가 도는 중에 팀원이 같은 폴더로 `serve.py --once`를 돌리면, 두 프로세스가 같은 작업(가장 새 커밋의 탐지 성능)을 잡고 서로의 `.work`와 체크아웃을 지운다. 먼저 돌던 쪽의 샤드가 출력 폴더를 잃거나 detector를 import하지 못해 실패로 기록되고, `POST /api/refresh?retry=1` 전까지 다시 돌지 않는다.
- **재현**: 결과가 없는 커밋이 남은 데이터 폴더에 `python3 dashboard/serve.py --once --data-dir <폴더> --repo <PromptGuard 경로>`를 두 개 동시에 띄운다. 두 번째가 시작하자마자 첫 번째의 `results/detection/<키>.work/`가 지워진다. 실제로 돌리지 않고 코드 경로로 확인했다.
- **고칠 방향**: 서비스 모드와 `--once`는 시작할 때 데이터 폴더의 잠금 파일(예: `fcntl.flock`으로 `<data_dir>/.lock`)을 잡고, 못 잡으면 이유를 출력하고 바로 끝낸다. 종료 코드는 serve.py의 `RESTART`(75)와 겹치지 않게 정한다. `--serve-only`와 `--export`는 읽기만 하니 잠그지 않는다. 서버는 Linux라 `fcntl`이면 된다.
- **끝 기준**: 잠금이 잡힌 상태에서 두 번째 프로세스가 메시지와 함께 바로 끝나는 테스트가 있다.

## 6. 예시 창과 태그가 샤드 나눔에 따라 달라진다

- **어디**: [collect.py](pipeline/collect.py) `Collector.payload()`(149행)가 샤드 안에서 창을 자른다(160행 `windows(source["text"], spans)`). 이때 그 item에서, 그 샤드 안에서 아직 버킷에 남아 있는 모든 후보의 초점(focus)을 함께 묶는다. `merge()`(200행)는 샤드 결과 가운데 전체 상위 후보만 남기지만, 창은 샤드 단계에서 이미 정해졌다.
- **증상**: 어떤 예시를 고를지는 샤드와 무관하다(순위가 item id의 해시). 하지만 창 범위와 태그는 같은 샤드에 어떤 item이 함께 있었는지에 따라 달라진다. `--jobs`나 데이터셋 크기가 바뀌면 같은 예시의 창이 달라진다. 다른 버킷 후보의 초점까지 창에 들어가면 태그가 늘어, 고르지도 않은 탭(예: '과잉 마스킹')에 나온다. 모듈 문서 문자열과 README는 샤드와 무관하다고 적고 있다. 숫자(셀)는 영향이 없다.
- **재현** (저장소 루트에서 `python3 windows_repro.py`): 같은 세션들을 샤드 1개와 2개로 나눠 돌린다(`per_bucket=1`). 대상 세션에는 놓친 정답(100–110)과 과잉 마스킹(500–505)이 함께 있고, 과잉 마스킹 버킷에서는 다른 세션에 밀린다.
  ```python
  import sys
  sys.path.insert(0, "dashboard")
  from pipeline import collect
  from evaluation.adapters.base import ItemOutput
  from evaluation.dataset.schema import GoldSpan, Item, Session
  from evaluation.run import evaluate_sessions
  from evaluation.scorer.edits import Edit, apply_edits

  DATASET = "repro"
  text = ("x" * 79 + "\n") * 10  # 800자, 짧은 줄
  names = [f"s{i}" for i in range(200)]
  target = max(names, key=lambda name: collect.rank_of(DATASET, name, 0))  # 순위가 가장 나빠 fp 버킷에서 밀린다
  others = [name for name in names if name != target][:3]
  sessions = [Session(target, [Item(0, "t", "tool_output", text)], [GoldSpan(0, 0, 100, 110, "PASSWORD")])]
  sessions += [Session(name, [Item(0, "t", "tool_output", text)], []) for name in others]


  class Adapter:  # 모든 세션의 500-505를 가린다: 정답과 겹치지 않으니 과잉 마스킹(PASSWORD로 셈)
      name = "repro"

      def describe(self):
          return {}

      def run_session(self, session):
          edits = [Edit(500, 505, "[PASSWORD_1]")]
          return {0: ItemOutput(0, apply_edits(text, edits), edits)}


  def shard_payload(part):
      result = evaluate_sessions(part, Adapter())
      collector = collect.Collector(DATASET, lambda meta: "-", per_bucket=1)
      for session, score in zip(part, result.scores):
          collector.add(session, session.items[0], score, result.outputs[(session.session_id, 0)])
      payload = collector.payload()
      payload.update(counts=result.metrics["counts"], lines_total=result.metrics["lines_total"])
      return payload


  for label, parts in (("one shard", [sessions]), ("two shards", [sessions[:1], sessions[1:]])):
      merged = collect.merge([shard_payload(part) for part in parts], per_bucket=1)
      example = next(example for example in merged["examples"] if example["session"] == target)
      print(f"{label:10s}: window {example['offset']}-{example['offset'] + len(example['text'])}, tags {example['tags']}")
  ```
  작성 시점 출력:
  ```text
  one shard : window 0-319, tags ['PASSWORD:missed']
  two shards: window 0-719, tags ['PASSWORD:fp', 'PASSWORD:missed']
  ```
- **고칠 방향**: 창을 `merge()`에서 최종 선택 기준으로 자른다. 샤드는 후보마다 초점과, 버킷에 남은 item의 원문을 넘긴다. merge는 전체 상위 후보만으로 item별 초점을 모아 `windows()`를 부른다. 원문을 넘기기 부담스러우면, 후보마다 창을 따로 자르고 같은 item의 창끼리 묶지 않는 방법도 된다.
- **주의**: `collect.py`가 바뀌니 결과 키가 바뀌어 모든 커밋을 다시 평가한다.
- **끝 기준**: 위 스크립트의 두 줄이 같다. `tests/test_collect.py`의 샤드 불변성 테스트에 이 경우(한 item이 여러 버킷의 후보이고 일부 버킷에서만 밀리는 경우)를 넣고, 예시의 `id`, `offset`, `text`, `tags`까지 비교한다.

## 7. 지연의 timeout 기준과 설명이 따로 논다

- **어디**:
  - [latency.py](pipeline/latency.py) `evaluate()`(139행)는 m4.py에 `--timeout-ms`를 넘기지 않는다. 그래서 m4의 기본값 5000ms(`metric-latency/scripts/m4.py`의 `DEFAULT_TIMEOUT_MS`)를 쓰고, m4는 `promptguard.config.json`을 읽지 않는다.
  - 그런데 [repo.py](pipeline/repo.py) `EXPORT_PATHS`(28–29행)는 이 파일을 "metric-latency의 timeout용"이라며 꺼내기만 한다.
  - 화면([app.js](web/app.js) 1090행)은 라벨을 "5초 넘은 호출"로 고정하고, 설명에서는 "시스템의 탐지기 timeout"이라고 쓴다.
  - `headline()`(128행)의 `over_timeout`은 앙상블과 어댑터 단독 측정을 모두 더한 값이라, 앙상블만 보여 주는 패널과 기준이 다르다. 작성 시점에는 화면에 쓰이지 않고 `index.json`과 `meta.json`에만 남는다.
- **증상**: 커밋에서 `detectorTimeoutMs`를 바꾸면 "5초 넘은 호출" 수가 실제 시스템 기준과 어긋난다. `index.json`을 읽는 쪽은 `over_timeout`을 앙상블의 수로 오해한다.
- **고칠 방향**:
  1. `latency.evaluate()`가 꺼낸 체크아웃의 `promptguard.config.json`에서 `detectorTimeoutMs`를 읽어 `--timeout-ms`로 넘긴다. 파일이나 값이 없으면 5000을 쓴다.
  2. 그러면 지연 결과가 이 값에도 기대므로 지연 키에 넣는다. 탐지 결과까지 다시 돌지 않도록 `Commit.fingerprint`는 그대로 둔다. 예를 들어 `repo.commits()`가 `git show <sha>:promptguard.config.json`에서 값을 읽어 `Commit`에 두고, `service.jobs()`와 `write_index()`가 지연 키를 만들 때만 섞는다.
  3. `headline()`의 `over_timeout`은 앙상블 값만 쓴다.
  4. 화면 라벨을 `data.timeout_ms`로 만든다.
  5. `condense()`/`headline()`이 바뀌니 `LATENCY_VERSION`을 올린다.
- **끝 기준**: timeout을 3000으로 바꾼 커밋은 3000ms 기준으로 세고, 라벨도 그 값을 보여 준다. `tests/test_latency.py`의 m4 null 탐지기 실행에 timeout을 넘겨 확인하고, 지연 키가 timeout에 따라 달라지는지 `tests/test_service.py`에서 확인한다.

## 8. 저장소 경로에 tests 폴더가 끼면 채점 코드 지문이 고정된다

- **어디**: [runner.py](pipeline/runner.py) `code_fingerprint()`(81행)가 `"tests" not in path.parts`로 테스트 파일을 거른다. 그런데 `path`가 절대 경로다.
- **증상**: 저장소를 `/home/x/tests/promptguard-data`처럼 `tests`라는 폴더 아래에 두면 채점 코드 파일이 모두 걸러져 지문이 상수가 된다. 그러면 채점기를 고쳐도 결과를 다시 만들지 않는다.
- **고칠 방향**: `path.relative_to(METRIC_DETECTION).parts`로 판정한다. 보통 경로에서는 걸러지는 파일이 같아서 지문 값이 바뀌지 않는다(재평가 없음).
- **끝 기준**: `SCORING_CODE`와 `METRIC_DETECTION`을 `.../tests/...` 아래 임시 복사본으로 바꿔 끼운 테스트에서, 채점 코드 파일을 고치면 지문이 바뀐다.

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
