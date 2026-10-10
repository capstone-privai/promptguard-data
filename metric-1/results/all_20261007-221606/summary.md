# 지표 1 전체 평가

sweep 행의 recall, precision, f2, fp_per_1k_lines는 F2가 가장 높은 임계값(`best_f2_threshold`)의 값이다.

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.6562 | 0.6765 | 0.6602 | 72.8477 |  | 20261007-221606_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.6562 | 0.6765 | 0.6602 | 72.8477 |  | 20261007-221608_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.5938 | 0.8077 | 0.6270 | 33.1126 |  | 20261007-221609_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.2812 | 1.0000 | 0.3285 | 0.0000 |  | 20261007-221610_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261007-221610_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261007-221610_identity |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.6282 | 0.7647 | 0.6515 | 23.4261 |  | 20261007-221611_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.6923 | 0.7838 | 0.7089 | 23.4261 |  | 20261007-221612_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.6410 | 0.8438 | 0.6734 | 14.6413 |  | 20261007-221613_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.4103 | 1.0000 | 0.4651 | 0.0000 |  | 20261007-221614_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261007-221615_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261007-221615_identity |  |

## sessions_from_CredData.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.9728 | 0.3974 | 0.7543 | 31.2354 |  | 20261007-221615_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.9773 | 0.3962 | 0.7557 | 31.3717 |  | 20261007-221849_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.9711 | 0.9828 | 0.9735 | 0.3573 |  | 20261007-222018_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.4334 | 0.8491 | 0.4804 | 1.6341 |  | 20261007-222722_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261007-222725_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261007-222728_identity |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 |  | 20261007-222729_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 |  | 20261007-222732_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 |  | 20261007-222733_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.7000 | 1.0000 | 0.7447 | 0.0000 |  | 20261007-222735_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261007-222735_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261007-222735_identity |  |

## sessions_from_privesc-llm-data.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | pr_auc | run_dir | note |
|---|---|---|---|---|---|---|---|---|---|
| promptguard | predictor=mock | ok | 0.1671 | 0.2992 | 0.1833 | 21.5895 |  | 20261007-222735_promptguard_mock |  |
| credsweeper | ml=off | ok | 0.4985 | 0.4887 | 0.4965 | 28.7618 |  | 20261007-222810_credsweeper_ml-off_all |  |
| credsweeper | ml=on | ok | 0.4916 | 0.9160 | 0.5418 | 2.4859 |  | 20261007-222850_credsweeper_ml-on_all |  |
| gitleaks |  | ok | 0.1162 | 0.9944 | 0.1411 | 0.0363 |  | 20261007-223355_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 |  | 20261007-223357_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 |  | 20261007-223359_identity |  |
