# 탐지기 구성별 성능: 단일 모듈과 투표

PromptGuard 탐지기는 어댑터 세 개(CredSweeper, gitleaks, 자체 규칙 `promptguard-rules`)가 각자 찾은 값을 합의 규칙으로 묶는 앙상블이다(`src/detector/detector.json`, 기본은 `majority`). 이 문서는 어댑터를 하나만 쓸 때와 셋이 투표할 때 metric-detection 점수가 어떻게 달라지는지 모든 데이터셋에서 잰 결과다.

- 대상 실행: `metric-detection/results/all_20261014-023225` (2026-10-14)
- 시스템: `promptguard-claude-demoV0@8973016`의 탐지기, CredSweeper 1.19.0, gitleaks 8.30.1
- 채점: [정확 일치 판정](../README.md#판정). 비밀값만 정확히 가려야 성공이고, 채점하는 채널은 `prompt`, `instructions`, `tool_output`이다
- 다시 돌리기: `python metric-detection/scripts/run_all.py --ensemble --systems promptguard --jobs 3`. 구성마다 `evaluate.py run --system promptguard --detectors … --consensus …`를 따로 실행한다

## 구성

시스템 코드와 설정 파일은 고치지 않는다. 채점기가 시스템의 `load_detector()`로 앙상블을 만든 뒤 고른 어댑터만 남기고(`--detectors`), 합의 규칙은 시스템이 받는 값을 그대로 넘긴다(`--consensus`). 어느 어댑터가 투표했고 몇 표가 필요했는지는 각 실행의 `run_meta.json`의 `system.detector`에 남는다.

| 구성 | 투표하는 어댑터 | 필요한 표 |
|---|---|---|
| CredSweeper 단독 | `credsweeper` (CredSweeper 기본 규칙 + `credsweeper-rules.yaml`) | 1 |
| gitleaks 단독 | `gitleaks` (기본 설정) | 1 |
| 자체 규칙 단독 | `promptguard-rules` | 1 |
| 셋, any | 셋 모두 | 1 |
| 셋, majority (시스템 기본) | 셋 모두 | 2 |
| 셋, unanimous | 셋 모두 | 3 |

투표에서는 위치가 조금이라도 겹치면 같은 값에 표를 준 것으로 본다. 통과한 탐지는 각자의 구간을 유지하고 겹치는 것끼리 합쳐진다. `셋, majority`는 [전체 실행](../results/all_20261014-021351/summary.md)의 PromptGuard와 아홉 데이터셋 모두에서 같은 점수가 나왔다.

## 결과

데이터셋 이름에서 `sessions_from_`을 뺐다. 정답 수가 적은 데이터는 점수 하나가 크게 흔들린다(SWE-Gym 2개, example 10개, sessions 32개, openhands-feedback 45개).

### recall

| 구성 | sessions | sessions_2 | CredData | Nemotron-PII | SWE-Gym | example | noseyparker | openhands | privesc |
|---|---|---|---|---|---|---|---|---|---|
| CredSweeper 단독 | 0.562 | 0.667 | 0.442 | 0.205 | 1.000 | 0.700 | 0.661 | **0.978** | **0.963** |
| gitleaks 단독 | 0.281 | 0.458 | 0.364 | 0.093 | 1.000 | 0.800 | 0.601 | 0.111 | 0.254 |
| 자체 규칙 단독 | 0.594 | 0.653 | 0.297 | 0.170 | 1.000 | 0.600 | 0.593 | 0.867 | 0.923 |
| 셋, any | **0.688** | **0.708** | **0.662** | **0.231** | 1.000 | **0.900** | **0.798** | **0.978** | 0.955 |
| 셋, majority | 0.531 | 0.639 | 0.302 | 0.175 | 1.000 | 0.700 | 0.624 | 0.889 | 0.942 |
| 셋, unanimous | 0.219 | 0.417 | 0.140 | 0.055 | 1.000 | 0.500 | 0.422 | 0.044 | 0.232 |

### precision

| 구성 | sessions | sessions_2 | CredData | Nemotron-PII | SWE-Gym | example | noseyparker | openhands | privesc |
|---|---|---|---|---|---|---|---|---|---|
| CredSweeper 단독 | 0.913 | 0.845 | 0.273 | 0.633 | 0.003 | 1.000 | 0.781 | 0.091 | 0.202 |
| gitleaks 단독 | **1.000** | **1.000** | 0.780 | 0.628 | 0.111 | **1.000** | 0.812 | **0.714** | 0.991 |
| 자체 규칙 단독 | 0.957 | 0.862 | 0.199 | **0.703** | 0.001 | **1.000** | 0.694 | 0.058 | 0.624 |
| 셋, any | 0.900 | 0.783 | 0.201 | 0.623 | 0.001 | **1.000** | 0.688 | 0.049 | 0.196 |
| 셋, majority | **1.000** | 0.940 | 0.376 | 0.695 | 0.003 | **1.000** | 0.749 | 0.160 | 0.840 |
| 셋, unanimous | **1.000** | **1.000** | **0.983** | 0.642 | **0.500** | **1.000** | **0.931** | 0.667 | **0.999** |

### F2

| 구성 | sessions | sessions_2 | CredData | Nemotron-PII | SWE-Gym | example | noseyparker | openhands | privesc |
|---|---|---|---|---|---|---|---|---|---|
| CredSweeper 단독 | 0.609 | 0.696 | 0.393 | 0.237 | 0.012 | 0.745 | 0.682 | 0.332 | 0.550 |
| gitleaks 단독 | 0.328 | 0.514 | 0.407 | 0.112 | 0.385 | 0.833 | 0.634 | 0.134 | 0.298 |
| 자체 규칙 단독 | 0.642 | 0.686 | 0.271 | 0.201 | 0.006 | 0.652 | 0.610 | 0.228 | 0.842 |
| 셋, any | **0.722** | **0.722** | **0.454** | **0.265** | 0.006 | **0.918** | **0.773** | 0.203 | 0.538 |
| 셋, majority | 0.586 | 0.683 | 0.314 | 0.206 | 0.014 | 0.745 | 0.646 | **0.465** | **0.919** |
| 셋, unanimous | 0.259 | 0.472 | 0.169 | 0.067 | **0.833** | 0.556 | 0.473 | 0.055 | 0.274 |

### 1,000줄당 과잉 마스킹

정답과 한 글자도 겹치지 않는 edit의 수다. 정답보다 넓게 가린 edit(`over`)는 세지 않는다.

| 구성 | sessions | sessions_2 | CredData | Nemotron-PII | SWE-Gym | example | noseyparker | openhands | privesc |
|---|---|---|---|---|---|---|---|---|---|
| CredSweeper 단독 | 13.25 | 14.22 | 68.23 | 2.98 | 1.50 | 0.00 | 53.52 | 1.54 | 192.99 |
| gitleaks 단독 | 0.00 | 0.00 | 5.79 | 1.19 | 0.03 | 0.00 | 38.50 | 0.01 | 0.02 |
| 자체 규칙 단독 | 6.62 | 11.06 | 75.53 | 1.87 | 3.16 | 0.00 | 81.69 | 2.24 | 27.96 |
| 셋, any | 19.87 | 22.12 | 116.98 | 3.30 | 3.34 | 0.00 | 107.98 | 3.03 | 199.55 |
| 셋, majority | 0.00 | 3.16 | 31.39 | 1.65 | 1.32 | 0.00 | 57.28 | 0.74 | 8.68 |
| 셋, unanimous | 0.00 | 0.00 | 0.25 | 1.08 | 0.00 | 0.00 | 6.57 | 0.00 | 0.01 |

## 읽는 법

- **모든 데이터에서 가장 나은 구성은 없다.** `any`는 recall이 가장 높고 과잉 마스킹도 가장 많다. `unanimous`는 그 반대다. `majority`는 그 사이에 있다.
- **`any`가 recall을 올리는 것은 어댑터마다 찾는 값이 달라서다.** CredData에서 CredSweeper 단독 0.442, gitleaks 단독 0.364인데 `any`는 0.662다. Nosey Parker도 0.661, 0.601에서 0.798이 된다. 대신 과잉 마스킹도 각 어댑터의 것이 모두 더해진다. privesc는 1,000줄당 200번, openhands-feedback은 3번이다.
- **`majority`는 privesc에서 가장 좋다(F2 0.919).** privesc의 정답 6,804개 중 4,734개는 CredSweeper와 자체 규칙이 함께 찾고, 1,590개는 셋이 모두 찾는다. 반면 두 어댑터의 과잉 마스킹은 서로 다른 자리에서 나온다. 그래서 두 표를 요구하면 recall은 0.963에서 0.942로 조금만 잃고, 과잉 마스킹은 1,000줄당 193번에서 8.7번으로 준다. openhands-feedback에서도 `majority`의 F2가 가장 높다.
- **CredData와 Nosey Parker에서는 `majority`가 CredSweeper 단독보다 recall이 낮다**(0.442 → 0.302, 0.661 → 0.624). 한 어댑터만 찾는 값이 많아서 두 표를 받지 못한다. CredData의 정답 15,596개 중 CredSweeper만 찾은 값이 2,196개, gitleaks만 찾은 값이 3,483개다. CredSweeper 단독에서 정확히 가렸는데 `majority`에서 놓친 2,201개 가운데 2,165개가 CredSweeper 혼자 찾은 값이다. `any`의 recall이 높은 것도 이 값들을 모두 살리기 때문이다.
- **투표로 통과해도 `over`가 될 수 있다.** 두 어댑터가 같은 값을 다른 경계로 잡으면(한쪽은 `key=value`, 다른 쪽은 값만) 통과한 구간을 합쳐 가리므로 정답보다 넓어진다. CredSweeper 단독에서는 정확히 가렸지만 `majority`에서 이렇게 `over`가 된 정답이 CredData에서 36개, privesc에서 63개다.
- **`unanimous`는 gitleaks가 병목이다.** recall이 gitleaks 단독보다도 낮다(privesc 0.232, openhands-feedback 0.044). precision은 거의 1이다.
- **실제 트래픽의 과잉 마스킹**(SWE-Gym, openhands-feedback): gitleaks 단독은 1,000줄당 0.03번, 0.01번이고, `majority`는 1.32번, 0.74번이다. 단독 어댑터 가운데서는 자체 규칙(3.16번, 2.24번)이 가장 많이 가린다. 이런 과잉 마스킹이 작업에 주는 영향은 metric-task로 본다.

## 주의할 점

- **openhands-feedback의 정답 후보는 CredSweeper와 gitleaks가 냈다.** 두 어댑터와 그 합(`any`)의 recall이 높게 나오는 쪽으로 기운다. 이 데이터는 precision과 과잉 마스킹으로 본다([README_openhands-feedback.md](../README_openhands-feedback.md)).
- **Nosey Parker의 정답 경계는 Nosey Parker 규칙이 정했다.** 다른 탐지기가 값을 다르게 자르면 다 가려도 `over`(실패)가 된다([README_noseyparker.md](../README_noseyparker.md)).
- **CredData의 precision은 하한값이다**([README_CredData.md](../README_CredData.md#xf를-음성으로-쓸-때-유의할-점)).
- **privesc의 줄 수는 작게 잡힌다.** `tool_output`이 JSON 한 줄이라 1,000줄당 수치가 크게 나온다. 다른 데이터와 비교하지 않는다.
- **2개 조합은 재지 않았다.** CredSweeper + gitleaks 같은 2개 조합의 `any`·`unanimous`는 `--pg-configs credsweeper+gitleaks@any`처럼 따로 돌린다.
- **실행 시간.** gitleaks 어댑터는 텍스트마다 하위 프로세스를 띄운다. 그래서 gitleaks가 들어간 구성은 privesc에서 25~36분, CredData에서 20분 넘게 걸렸다(3개 동시 실행). gitleaks가 빠진 단독 구성은 privesc에서 8~44초였다. 지연 시간 비교는 metric-latency로 한다.
