# 지표 1 전체 평가

sweep 행의 recall, precision, f2, fp_per_1k_lines는 F2가 가장 높은 임계값(`best_f2_threshold`)의 값이다.

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.6562 | 0.6765 | 0.6602 | 72.8477 |  | 20261008-010650_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.6562 | 0.6765 | 0.6602 | 72.8477 |  | 20261008-010650_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.5938 | 0.8077 | 0.6270 | 33.1126 |  | 20261008-010650_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.3125 | 1.0000 | 0.3623 | 0.0000 |  | 20261008-010650_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-010651_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-010651_identity |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.6282 | 0.7647 | 0.6515 | 23.4261 |  | 20261008-010651_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.6923 | 0.7838 | 0.7089 | 23.4261 |  | 20261008-010652_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.6410 | 0.8438 | 0.6734 | 14.6413 |  | 20261008-010652_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.4744 | 1.0000 | 0.5301 | 0.0000 |  | 20261008-010652_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-010652_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-010652_identity |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 |  | 20261008-010653_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 |  | 20261008-010653_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 |  | 20261008-010653_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 |  | 20261008-010654_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261008-010654_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261008-010654_identity |  |
