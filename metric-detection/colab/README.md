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
- 채점은 `--use ml_eval`로 한다. 학습·검증 split 세션이 섞인 데이터셋은 실행 전에 거부된다.
