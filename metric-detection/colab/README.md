# Colab에서 ML 탐지 평가

[`evaluate_ml.ipynb`](evaluate_ml.ipynb)는 PromptGuard를 체크아웃에 설정된 그대로 두고, 플러그인 스위치 `PG_DETECTOR_ENABLE`로 ML 모듈(`ml-v9`, `ml-qwen`)만 켜서 metric-detection 채점을 돌린다. 같은 데이터로 ML 없이도 한 번 돌려 비교표를 만든다.

## 데이터 올리기

`data_test/`와 `data_answer/`는 git에 없다(비밀값 형식의 가짜·수집 데이터). 데이터를 만든 서버에서 압축해 Google Drive의 `MyDrive/promptguard/`에 올린다.

```bash
# 1만 개 표본 (runs/ml-evaluations/sample_evaluation.py로 뽑은 것, 약 3MB)
tar -czf runs/colab/pg-data-10k.tar.gz -C runs/ml-evaluations/sample-10k-v1 data_test data_answer manifest.json
# 전체 (item 약 11만 개, 약 31MB)
tar -czf runs/colab/pg-data-full.tar.gz -C metric-detection data_test data_answer
```

압축 파일에는 비밀값 형식의 문자열이 들어 있다. 공유 폴더나 공개 위치에 두지 않는다. 결과 폴더(`per_edit.jsonl` 등)도 마찬가지다.

## 실행

1. Colab에서 `evaluate_ml.ipynb`를 연다(GitHub에서 열기: `capstone-privai/promptguard-data`, 경로 `metric-detection/colab/evaluate_ml.ipynb`).
2. 런타임 유형을 GPU로 바꾼다. Qwen은 `device: auto`라 GPU를 쓴다. v9는 detector.json에서 `cpu`로 고정돼 있고, 노트북의 `V9_DEVICE = "cuda"`로 이 Colab 사본에서만 바꿀 수 있다.
3. ① 설정 셀에서 `DATA_ARCHIVE`, `ENABLE`을 고르고 위에서부터 차례로 실행한다.

## 결과를 읽을 때

- 노트북은 `--require-adapters`로 실행한다. ML 모듈이 패키지나 가중치 문제로 빠지면 점수를 내지 않고 이유를 출력하며 멈춘다. 플러그인에서 ML 모듈은 선택 모듈이라, 이 옵션이 없으면 빠져도 점수가 정상처럼 나온다.
- `blocked`는 탐지기 오류(ML timeout `ADAPTER_FAILURE` 등)로 Final Guard가 요청을 막았다고 본 item 수다. 그 item의 정답은 노출이 아니라 과잉 마스킹(`over`)으로 채점된다. ML을 켠 쪽에서만 이 수가 크면 ML 모듈의 timeout(v9 4초, Qwen 25초)에 걸린 것이다. 자세한 규칙은 [evaluation/README.md](../evaluation/README.md)의 "탐지기 실패"에 있다.
- 채점은 `--use ml_eval`로 한다. `meta.split`이 `train`·`val`인 세션은 거부되지만, privesc-llm-data 원본(`sessions_from_privesc-llm-data`, split 이름이 `training`·`validation`)은 통과한다. 이 원본에는 ML 학습 시나리오가 들어 있으니 압축 파일에 넣지 않거나 그 행은 읽지 않는다(README의 데이터셋 표).

## 중간발표 탐지 성능 보고서

[`report_midterm.ipynb`](report_midterm.ipynb)는 모든 데이터셋을 최신 라벨 기준으로 새로 만들어 전수 채점하고 `report/detection/`에 다섯 파일(README.md, datasets.md, detection.md, miss_groups.md/.json, slide_numbers.md)을 쓴다. 지연은 재지 않는다.

- 시스템 코드와 채점기 코드는 고치지 않는다. 어댑터 단독·기존 3개 합집합·기존 다수결은 노트북 맨 위의 헬퍼(`pg_report.py`)가 시스템의 `pgdetector` 클래스로 조립해 채점기(`execute_run`)에 넘긴다.
- 이미 따로 분석한 구성은 ① `ALREADY_DONE`에 넣어 빼고, 그 결과가 필요한 칸은 —와 이유로 남는다(기본: CredSweeper ML off, gitleaks 단독, 어댑터: 자체 규칙).
- 원본 받기(CredData 수십 분)와 채점은 백그라운드로 돌고 로그를 남긴다. 만든 데이터와 끝난 채점 조각은 Drive에 남아 런타임이 끊겨도 이어서 한다.
- "시스템" 행은 실제 worker의 HTTP 결과와 채점기 안 결과를 비교하고 Mod 치환 계약 테스트가 통과해야 채운다.
- "시스템 + v9", "시스템 + Qwen"은 시스템 기본 설정에 ML 모듈 하나를 플러그인 스위치(`PG_DETECTOR_ENABLE`)로 켠 구성이다. 모듈이 실제로 돌지 않으면 그 실행은 점수를 내지 않고 멈추고, ⑥에서 먼저 작은 조각으로 확인한다. Qwen 때문에 GPU 런타임을 쓴다. Qwen은 `models/qwen-span-v3` 번들을 쓴다(① `QWEN_BUNDLE`). 시스템 설정은 v2를 가리키므로, ②가 받은 시스템 사본의 `detector.json`에서 그 값만 바꾸고 보고서 README에 적는다.
- 채점은 두 단계다. 1단계는 데이터셋마다 조각 1개(seed 20261029)를 시스템·시스템 + v9·시스템 + Qwen으로 채점해 `ml_sample.md`에 비교한다. 2단계는 ML 두 구성을 뺀 나머지 전부를 전체 조각으로 채점한다(본 보고서의 ML 두 행은 조각 미완료로 —). `R.start`는 시작 전에 이전 스케줄러를 모두 끈다. 스케줄러는 셀 중단·커널 재시작에도 살아 있어서, 둘이 겹치면 진행 표시가 섞이고 서로의 결과를 지운다.
- ML을 켠 두 행을 빼면 모든 구성은 모든 데이터셋으로 채점한다: 합성 3종, CredData, Nemotron-PII, Nosey Parker, openhands-feedback, SWE-Gym, privesc-llm-data 평가용 변환본(`sessions_from_privesc-llm-data`, 2,200세션), ML 평가 test·test_ood. ML 평가 test_ood는 privesc-llm-data와 같은 세션이라 전체(micro)에서는 빼고 센다.
- ML 평가 test는 ML 학습 데이터 빌드 전체(손 템플릿 hand_v1 800세션, v1이 있으면 v1 전체), ML 평가 test_ood는 privesc 10개 시나리오 전체 2,200세션이다(split을 나누지 않음). 채점기가 train·val split을 거부하므로 평가용 사본에서 split을 `test`로 바꾸고 원래 값은 `meta.ml_split`에 남긴다.
- LLM 템플릿(v1)은 git에 없다. 파일이 있으면 ① `V1_TEMPLATES`에 경로를 넣는다.
- 분류 검수(무작위 30개)는 사람이 ⑨에서 판정을 넣는다. 넣기 전까지 보고서에는 "검수 미완료"로 나온다.
