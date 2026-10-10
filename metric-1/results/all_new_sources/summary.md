# 지표 1 전체 평가

sweep 행의 recall, precision, f2, fp_per_1k_lines는 F2가 가장 높은 임계값(`best_f2_threshold`)의 값이다.

## sessions_from_Nemotron-PII.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.2062 | 0.7097 | 0.2402 | 3.1021 |  | 20261008-031313_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.3086 | 0.6523 | 0.3449 | 6.0519 |  | 20261008-031313_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.2121 | 0.7193 | 0.2469 | 3.0450 |  | 20261008-031313_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.0975 | 0.7570 | 0.1181 | 1.1514 |  | 20261008-031323_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-031323_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-031324_identity |  |

## sessions_from_openhands-feedback.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.9574 | 0.1991 | 0.5435 | 0.5261 |  | 20261008-031324_promptguard_mock |  |
| credsweeper | ml=off | ok | 1.0000 | 0.1382 | 0.4451 | 0.8516 |  | 20261008-031324_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.9787 | 0.4182 | 0.7718 | 0.1860 |  | 20261008-031341_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.1064 | 0.7143 | 0.1282 | 0.0058 |  | 20261008-031350_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-031345_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-031345_identity |  |

## sessions_from_SWE-Gym.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 1.0000 | 0.0039 | 0.0190 | 0.8533 |  | 20261008-031346_promptguard_mock |  |
| credsweeper | ml=off | ok | 1.0000 | 0.0027 | 0.0135 | 1.2122 |  | 20261008-031351_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 1.0000 | 0.0075 | 0.0365 | 0.4366 |  | 20261008-031406_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 1.0000 | 0.0909 | 0.3333 | 0.0331 |  | 20261008-031421_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-031421_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-031422_identity |  |

## sessions_from_noseyparker.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.7749 | 0.7584 | 0.7716 | 88.2629 |  | 20261008-031422_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.7892 | 0.7487 | 0.7807 | 92.9577 |  | 20261008-031424_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.7265 | 0.8464 | 0.7477 | 46.0094 |  | 20261008-031424_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.6268 | 0.8871 | 0.6659 | 26.2911 |  | 20261008-031426_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-031427_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-031427_identity |  |
