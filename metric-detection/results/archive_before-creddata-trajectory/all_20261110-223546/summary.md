# metric-detection 전체 평가

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7500 | 0.9000 | 0.7759 | 19.8675 | 20261110-223546_promptguard |  |
| credsweeper | ml=off | ok | 0.6875 | 0.6471 | 0.6790 | 72.8477 | 20261110-223546_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6562 | 0.8077 | 0.6818 | 33.1126 | 20261110-223546_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.3125 | 1.0000 | 0.3623 | 0.0000 | 20261110-223550_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-223550_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-223550_identity |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7361 | 0.7826 | 0.7450 | 22.1169 | 20261110-223550_promptguard |  |
| credsweeper | ml=off | ok | 0.7083 | 0.7429 | 0.7150 | 25.2765 | 20261110-223550_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6528 | 0.8000 | 0.6777 | 15.7978 | 20261110-223552_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.4722 | 1.0000 | 0.5280 | 0.0000 | 20261110-223558_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-223558_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-223558_identity |  |

## sessions_from_CredData.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | ok | 0.7500 | 0.3289 | 0.5971 | 34.7114 | 20261110-223622_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6600 | 0.7231 | 0.6717 | 5.6778 | 20261110-223657_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.3975 | 0.8296 | 0.4437 | 1.8260 | 20261110-224040_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-224049_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-224057_identity |  |

## sessions_from_Nemotron-PII.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | ok | 0.2585 | 0.5519 | 0.2892 | 5.7464 | 20261110-225316_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.1914 | 0.6697 | 0.2233 | 3.0118 | 20261110-225332_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.0710 | 0.5711 | 0.0861 | 1.1952 | 20261110-225445_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-225445_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-225446_identity |  |

## sessions_from_SWE-Gym.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | pending |  |  |  |  |  |  |
| credsweeper | ml=on | pending |  |  |  |  |  |  |
| gitleaks |  | pending |  |  |  |  |  |  |
| oracle |  | pending |  |  |  |  |  |  |
| identity |  | pending |  |  |  |  |  |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | pending |  |  |  |  |  |  |
| credsweeper | ml=on | pending |  |  |  |  |  |  |
| gitleaks |  | pending |  |  |  |  |  |  |
| oracle |  | pending |  |  |  |  |  |  |
| identity |  | pending |  |  |  |  |  |  |

## sessions_from_noseyparker.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | pending |  |  |  |  |  |  |
| credsweeper | ml=on | pending |  |  |  |  |  |  |
| gitleaks |  | pending |  |  |  |  |  |  |
| oracle |  | pending |  |  |  |  |  |  |
| identity |  | pending |  |  |  |  |  |  |

## sessions_from_openhands-feedback.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | pending |  |  |  |  |  |  |
| credsweeper | ml=on | pending |  |  |  |  |  |  |
| gitleaks |  | pending |  |  |  |  |  |  |
| oracle |  | pending |  |  |  |  |  |  |
| identity |  | pending |  |  |  |  |  |  |

## sessions_from_trajectory.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | pending |  |  |  |  |  |  |
| credsweeper | ml=off | pending |  |  |  |  |  |  |
| credsweeper | ml=on | pending |  |  |  |  |  |  |
| gitleaks |  | pending |  |  |  |  |  |  |
| oracle |  | pending |  |  |  |  |  |  |
| identity |  | pending |  |  |  |  |  |  |
