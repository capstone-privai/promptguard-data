# detector + ML 자동 평가 연결

`--ml-config`는 두 모드를 지원한다. 현재 공개된 **span-detector-v9는 `span_union` 모드**로 규칙 탐지와 ML 원문 탐지를 합친다([v9 연결](#span-detector-v9-규칙--ml-합집합)). 기존 후보별 분류기는 `candidate` 모드다. ML 설정이 없으면 기존 규칙 평가를 실행한다.

`candidate` 모드에서는 detector 후보를 JSONL 프로세스에 보내 `MASK` 후보만 가리고, `KEEP` 후보는 원문을 유지한다. 후보가 없는 item은 ML을 호출하지 않는다. 이 모드의 ML은 detector가 놓친 비밀을 새로 찾을 수 없어 최종 recall의 상한이 1차 후보 recall이다. 아래 KEEP/MASK 계약은 이 모드의 기본 계약이며 v9는 마지막 절의 span 응답 계약을 사용한다.

모델 파일 형식과 라이브러리는 추론 명령 안에서 처리한다. 이 저장소는 모델을 학습하지 않는다. 학습 담당자는 체크포인트·토크나이저·추론 코드와 아래 프로토콜을 구현한 명령을 전달하면 된다.

## 모델 전달과 실행

예를 들어 `runs/models/` 아래에 다음처럼 둔다. 모델 설정은 `bundle` 바깥에 두고, 실행에 영향을 주는 파일은 모두 bundle 안에 넣는다. 외부 라이브러리는 고정된 별도 Python 환경에 설치하고 모델을 바꿀 때 `model_id`도 바꾼다.

```text
runs/models/
  model.json
  finetuned-v1/
    infer_jsonl.py
    requirements.lock
    checkpoint/...
    tokenizer/...
```

`model.json` 예시(경로와 데이터셋 이름은 실제 전달물에 맞춘다):

```json
{
  "model_id": "finetuned-v1",
  "bundle": "finetuned-v1",
  "command": ["/absolute/path/to/model-venv/bin/python", "-u", "{bundle}/infer_jsonl.py", "--checkpoint", "{bundle}/checkpoint"],
  "timeout_seconds": 120,
  "datasets": ["sessions_mleval_privesc_test_ood"]
}
```

`command`는 셸 문자열이 아닌 인자 배열이다. `{bundle}`은 평가용 사본의 절대 경로로 바뀐다. 추론 명령은 작업 폴더에 의존하지 않고, 가중치를 한 번 로딩한 뒤 stdin을 계속 읽는다. stdout에는 응답 JSONL만 쓰고 로그는 stderr에 쓴다. CPU/GPU 장치 선택과 `P(MASK)` 임계값은 추론 코드 또는 bundle 안의 설정에 고정한다.

```bash
python dashboard/serve.py --ml-config runs/models/model.json --jobs 1
# 기존 서버 설정에는 DASHBOARD_ML_CONFIG=/absolute/path/to/model.json 으로 지정해도 된다.
```

`--jobs`개 샤드마다 별도 모델 프로세스가 생긴다. GPU 메모리를 공유해야 하면 `--jobs 1`부터 사용한다. 명령에 지정한 모델 Python은 detector 평가용 `--python`과 별개다. ML 설정이 없으면 기존 detector 평가를 실행한다.

`datasets`는 반드시 비어 있지 않은 **평가용 데이터셋 파일 stem의 허용 목록**이다. `metric-detection/data_test/`에 해당 sessions 파일과 정답 파일이 모두 있어야 한다. 각 세션은 `ml_eval` 용도를 허용해야 하며 `train`·`val` split은 거부한다. privesc를 학습에 사용했다면 전체 `sessions_from_privesc-llm-data`를 평가 목록에 넣지 말고 학습 계획의 `ml_train_export.py`로 내보낸 heldout 세트를 사용한다. 위 예시 세트도 먼저 내보내야 하며 이 문서는 데이터나 모델 파일을 생성하지 않는다.

## JSONL 프로토콜 v1

요청 한 줄은 item 하나와 그 안의 후보 전체다. 위치는 Python 문자열과 같은 Unicode code point 기준의 `[start, end)`이다. 후보 값은 `text[start:end]`로 읽는다. 정답·학습 라벨은 추론 프로세스에 전달하지 않는다.

```json
{"version":1,"request_id":1,"session_id":"s1","item_id":0,"turn_id":"t0","channel":"tool_output","text":"password=demo-value","offset_unit":"code_points","candidates":[{"id":0,"start":9,"end":19,"type":"PASSWORD","rule_id":"example"}]}
```

응답은 같은 `version`·`request_id`와 각 후보의 결정을 정확히 하나씩 포함한다. 후보 순서는 달라도 되지만 ID가 중복되거나 누락되면 실패한다. `MASK`는 가림, `KEEP`는 유지다.

```json
{"version":1,"request_id":1,"decisions":[{"id":0,"label":"MASK"}]}
```

프로세스 종료, 시간 초과, 잘못된 응답은 평가 실패로 처리한다. 규칙 탐지 결과로 대체하지 않는다. 이전 MASK 값을 다른 item에 자동으로 다시 가리지 않으므로 이번 ML의 KEEP 결정을 뒤집지 않는다. 이 경로는 현재 Native Mod의 remask와 차이가 있으며 결과 메타데이터에 `remask:false`를 남긴다.

## 지연과 자동 재평가

ML 모드의 `detector_ms`는 **입력을 받은 시점부터 detector 후보 생성과 모든 후보의 최종 KEEP/MASK 결정이 끝날 때까지**다. JSON 파싱, 1차 탐지, Unicode 위치 변환, JSONL 전송·대기·추론을 포함한다. 후보가 없는 입력은 1차 탐지만 포함한다. HTTP 왕복과 응답 직렬화까지는 기존 `call_ms`로 따로 기록한다. 문자열 여러 개의 batch는 모든 item을 처리한 전체 시간을 기록한다.

가중치 로딩 등 최초 요청 비용은 cold 호출에, worker 프로세스 시작은 startup에 따로 남기며 반복 측정은 warm 지연이다. ML 프로세스가 첫 요청에 가중치를 로딩하는 구현이면 그 로딩은 cold 호출에 포함된다. 지연 측정에는 gitleaks 결과 캐시를 사용하지 않는다. Guard 재생도 ML이 판정한 최종 MASK 개수로 차단·캐시 동작을 결정한다. 합성·Guard 기록처럼 원래 채널 정보가 없는 지연 입력은 추론 요청에서 `tool_output` 채널로 보낸다.

bundle 내용·추론 명령·모델 ID·timeout·평가 목록이 바뀌면 다음 자동 확인에서 성능과 지연 결과 키가 바뀐다. 평가마다 모델 bundle을 사본으로 고정하고 계획의 해시와 대조한다. 사본을 뜨기 전에 모델이 바뀌면 작업을 다시 계획한다. 평가용 모델 사본은 종료 후 삭제하고 결과 파일에 가중치를 보관하지 않는다. 기존 규칙 전용 결과나 다른 모델의 결과는 현재 ML 결과로 표시하지 않는다. 모델 환경을 bundle 밖에서 변경했으면 `model_id`도 변경해야 한다.

## 검증

```bash
python -m unittest discover -s dashboard/tests -t dashboard
node --test dashboard/tests/test_web.js
```

가짜 모델의 JSONL 프로세스로 KEEP/MASK, Unicode 위치, 오류·timeout, 모델 사본·키 변경, ML 포함 HTTP 지연, 자동 평가 계획을 검증한다. 실제 모델 정확도는 학습된 bundle을 전달받아 heldout 세트에서 별도로 측정한다.

## span-detector-v9: 규칙 + ML 합집합

모델 저장소 `f6204b88`에서 공개한 `models/span-detector-v9`는 원문 BIO span 탐지기다. 현재 이 가중치는 **규칙 탐지와 ML 원문 탐지의 합집합**으로 연결한다. 설정에 `"mode": "span_union"`을 넣으면 기존 규칙 finding을 유지하고, ML이 단독으로 찾은 구간도 추가한다. 정확히 같은 구간은 중복 제거하고, 겹치는 구간은 최종 마스킹 직전에 합친다. 서로 인접하기만 한 구간은 합치지 않는다. 규칙 후보가 없는 item도 ML이 검사한다. Native Mod가 이미 가린 값을 같은 세션에서 다시 가리는 기존 remask 정책도 유지한다. `tool_input`은 기존대로 검사·채점하지 않는다.

`span_jsonl.py`를 bundle의 `infer_jsonl.py`로 복사하고 모델 커밋의 `src/`, `uv.lock`, 체크포인트 전체를 함께 넣는다. 명령 인자는 `--checkpoint {bundle}/checkpoint --source {bundle}/src --threads 2 --mode span_union`다. CPU 추론이며 저장된 `span_bundle.json`의 threshold를 그대로 사용한다. 토크나이저와 가중치는 로컬에서만 읽고 프로세스당 모델을 한 번 로딩한다. 현재 서버의 설정은 git에서 제외되는 `runs/models/span-v9-union.json`에 있다.

합집합 프로토콜의 요청은 앞의 v1 공통 필드와 원문 `text`, `offset_unit`을 사용하며 `candidates`가 필요 없다. 응답은 다음과 같다. 위치는 Unicode code point 기준이며 `score`는 유한한 0~1 값이어야 한다. 모델이 저장된 임계값을 적용한 뒤 반환하므로 평가기가 임계값을 다시 고르지 않는다.

```json
{"version":1,"request_id":1,"offset_unit":"code_points","spans":[{"start":9,"end":19,"score":0.9999}]}
```

합집합 모드의 지연은 입력 수신부터 **규칙 탐지 + ML 원문 탐지 + 최종 마스킹 구간 병합**까지 포함한다. 모델·원문 위치가 잘못되거나 한 단계가 실패하면 규칙 결과만으로 성공 처리하지 않는다. `span_counts`에는 rule/ML 후보 수, 병합 후 최종 구간 수, 규칙 후보와 전혀 겹치지 않는 ML-only 후보 수를 따로 남긴다. 넓은 ML 구간이 기존 규칙 정답을 더 넓게 가릴 수 있어, 후보 합집합이 최종 exact-span 성능 향상을 보장하지는 않는다.

이전의 후보별 KEEP/MASK 모드는 `mode` 생략 또는 `"mode": "candidate"`로 계속 사용할 수 있다. span 모델을 후보 겹침 게이트로 시험하려면 명령의 `--mode candidate`를 쓰지만, 이는 현재 선택된 합집합 평가와 다른 실험이다.

v9는 합성 데이터로 학습됐으며 기존 공개 평가 예시를 참고해 개발됐다. 기존 평가 데이터에서 측정한 결과는 새롭고 독립적인 holdout 성능으로 해석하지 않는다. 이 연결은 평가용이며 운영 detector의 기본 설정을 자동으로 바꾸지 않는다.
