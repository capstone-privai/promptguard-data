# Colab에서 Qwen v3 탐지 평가

[`evaluate_ml.ipynb`](evaluate_ml.ipynb)는 PromptGuard(promptguard-claude-demoV0)에 `ml-qwen`만 켠 구성 하나를 전체 데이터 8종으로 평가한다. 서버(ARM CPU, GPU 없음)에서는 약 20시간 걸리고 타임아웃 위험이 있어 이 구성만 Colab GPU로 옮겼다. 평가 경로는 서버 `runs/e2e-20261106/run_config.py`와 같은 `dashboard/pipeline/runner.evaluate`이고, 결과 `summary.json`은 `runs/e2e-20261106/report.py`로 같은 표를 만들 수 있다.

시스템·모델·채점기 커밋, 임계값, 데이터 해시, 패키지 버전은 노트북 ① 셀에 고정돼 있고 실행 중에 검증한다. 다르면 멈춘다.

③ 셀은 패키지를 설치한 뒤 `torchao`를 지운다. peft 0.21.2가 Colab의 torchao 0.10.0을 거부해 Qwen을 불러오지 못하기 때문이다. torchao는 양자화 전용이라 이 평가에 쓰지 않는다고 판단했고, 지운 경우와 안 지운 경우를 비교 검증하지는 않았다. 수정한 셀은 아직 Colab에서 그대로 실행해 보지 않았다(같은 명령을 VM에서 직접 실행해 평가를 돌렸다).

## 데이터 올리기

`data_test/`와 `data_answer/`는 git에 없다(비밀값 형식의 가짜·수집 데이터). 서버의 `runs/colab/pg-data-full-07cf988.tar.gz`(라벨 정제 후 현재 데이터 8종)를 Google Drive의 `MyDrive/promptguard/`에 그대로 올린다. sha256은 `1d762bbf187a259a0f13505201796bd43b57239a9f288ddcd447e4a78dca6944`이다. 옛 `pg-data-full.tar.gz`는 노트북의 해시 검사에서 멈춘다.

압축 파일에는 비밀값 형식의 문자열이 들어 있다. 공유 폴더나 공개 위치에 두지 않는다. Drive의 `qwen-v3-cca44c4/resume/`과 `results/*/examples/`도 마찬가지다. 서버의 `gitleaks-cache.sqlite`는 비밀값이 들어 있고 ARM 바이너리 해시로 키가 묶여 Colab에서 적중하지 않으므로 올리지 않는다.

## 실행

1. 채점기 커밋 `9bd0d37`이 GitHub에 있어야 한다. 이 노트북이 들어 있는 브랜치를 push하면 함께 올라간다.
2. Colab에서 `evaluate_ml.ipynb`를 열고 런타임 유형을 GPU로 바꾼다. GPU가 없으면 ③에서 멈춘다.
3. "모두 실행"으로 ⑦까지 본다. 작은 데이터 3종의 차단 건수, 호출당 시간, 예상 전체 시간이 나온다. 전체 실행은 `RUN_FULL = False`라 시작되지 않는다.
4. 숫자가 괜찮으면 ①에서 `RUN_FULL = True`로 바꾸고 ①, ⑧, ⑨를 실행한다. 끝나면 ⑩을 실행한다.

평가는 별도 프로세스로 돌아 셀을 중단하거나 브라우저를 닫아도 계속된다. 브라우저만 끊겼으면 ①과 ⑨를 실행한다. 런타임이 초기화됐으면 ①부터 다시 실행하고 ⑧로 이어 간다. 끝난 샤드는 Drive 체크포인트에서 복원하고, 돌던 샤드 하나만 다시 계산한다.

묶음별 표는 서버에서 만든다. Drive의 `qwen-v3-cca44c4/results/qwen/`에서 `summary.json`, `meta.json`, `RUN_NOTES.md`를 받아 `runs/e2e-20261106/results/qwen/`에 두고 `report.py base v10 qwen`을 실행한다.

## 결과를 읽을 때

- **서버 결과와 비교:** GPU에서 돌렸으므로 지연과 타임아웃 차단은 서버 결과와 직접 비교할 수 없다. 타임아웃(25초)은 그대로지만 서버에서라면 막혔을 입력이 통과할 수 있다. 조건은 결과 폴더의 `RUN_NOTES.md`에 함께 남는다.
- **설정 변경:** 시스템 사본의 `detector.json`에서 `ml-qwen.enabled`와 `ml-qwen.options.repository`만 바꾼다. 이 파일을 커밋 내용에서 같은 바이트로 다시 만들어 `system_fingerprint`가 재시작해도 같다.
- **Qwen이 빠진 샤드:** `ml-qwen`은 필수 어댑터가 아니어서, 샤드 프로세스에서 모델 로드가 실패하면 Qwen 없이 점수가 나온다. 노트북은 샤드가 끝날 때마다 이를 검사해 그런 샤드를 합치지 않고 멈춘다. 다시 시작하면 그 샤드만 다시 계산한다.
- **`blocked`:** 탐지기 오류나 타임아웃으로 Final Guard가 요청을 막았다고 본 item 수다. 그 item의 정답은 노출이 아니라 과잉 마스킹(`over`)으로 채점된다. 자세한 규칙은 [evaluation/README.md](../evaluation/README.md)의 "탐지기 실패"에 있다.
- **어댑터 실패 수:** 샤드 로그의 `어댑터:예외 형식`별 횟수다. 타임아웃은 `ml-qwen:RuntimeError`로 나오며 다른 Qwen 실패와 구분되지 않는다.

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
