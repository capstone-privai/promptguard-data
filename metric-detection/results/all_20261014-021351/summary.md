# metric-detection 전체 평가

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.5312 | 1.0000 | 0.5862 | 0.0000 | 20261014-021351_promptguard |  |
| credsweeper | ml=off | ok | 0.6250 | 0.6471 | 0.6293 | 72.8477 | 20261014-021351_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.5938 | 0.8077 | 0.6270 | 33.1126 | 20261014-021351_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.3125 | 1.0000 | 0.3623 | 0.0000 | 20261014-021352_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-021352_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-021352_identity |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.6389 | 0.9400 | 0.6826 | 3.1596 | 20261014-021352_promptguard |  |
| credsweeper | ml=off | ok | 0.6806 | 0.7429 | 0.6922 | 25.2765 | 20261014-021353_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6250 | 0.8000 | 0.6536 | 15.7978 | 20261014-021354_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.4722 | 1.0000 | 0.5280 | 0.0000 | 20261014-021354_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-021354_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-021355_identity |  |

## sessions_from_CredData.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.3017 | 0.3758 | 0.3141 | 31.3875 | 20261014-021355_promptguard |  |
| credsweeper | ml=off | ok | 0.9742 | 0.3950 | 0.7533 | 31.3717 | 20261014-021355_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.9709 | 0.9825 | 0.9732 | 0.3573 | 20261014-021356_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.4327 | 0.8477 | 0.4796 | 1.6341 | 20261014-021431_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-021435_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-021440_identity |  |

## sessions_from_Nemotron-PII.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.1754 | 0.6947 | 0.2062 | 1.6462 | 20261014-021441_promptguard |  |
| credsweeper | ml=off | ok | 0.2553 | 0.5396 | 0.2854 | 6.0519 | 20261014-021608_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.1999 | 0.6781 | 0.2328 | 3.0450 | 20261014-021620_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.0758 | 0.5884 | 0.0918 | 1.1514 | 20261014-021703_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-021703_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-021704_identity |  |

## sessions_from_SWE-Gym.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 1.0000 | 0.0029 | 0.0142 | 1.3164 | 20261014-021704_promptguard |  |
| credsweeper | ml=off | ok | 1.0000 | 0.0033 | 0.0161 | 1.1556 | 20261014-021904_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 1.0000 | 0.0077 | 0.0373 | 0.4880 | 20261014-021959_credsweeper_ml-on |  |
| gitleaks |  | ok | 1.0000 | 0.1111 | 0.3846 | 0.0303 | 20261014-022107_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-022108_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-022108_identity |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7000 | 1.0000 | 0.7447 | 0.0000 | 20261014-022109_promptguard |  |
| credsweeper | ml=off | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 | 20261014-022112_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 | 20261014-022114_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 | 20261014-022116_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-022117_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-022117_identity |  |

## sessions_from_noseyparker.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.6239 | 0.7492 | 0.6455 | 57.2770 | 20261014-022117_promptguard |  |
| credsweeper | ml=off | ok | 0.7778 | 0.7386 | 0.7696 | 92.9577 | 20261014-022150_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.7151 | 0.8339 | 0.7361 | 46.0094 | 20261014-022153_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.6040 | 0.8548 | 0.6416 | 26.2911 | 20261014-022210_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-022210_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-022210_identity |  |

## sessions_from_openhands-feedback.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.8889 | 0.1600 | 0.4651 | 0.7366 | 20261014-022210_promptguard |  |
| credsweeper | ml=off | ok | 0.9778 | 0.1905 | 0.5353 | 0.6555 | 20261014-022438_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.9778 | 0.6027 | 0.8696 | 0.1022 | 20261014-022501_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.1111 | 0.7143 | 0.1337 | 0.0070 | 20261014-022535_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-022536_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-022536_identity |  |

## sessions_from_privesc-llm-data.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.9415 | 0.8397 | 0.9192 | 8.6808 | 20261014-022537_promptguard |  |
| credsweeper | ml=off | ok | 0.5825 | 0.4872 | 0.5605 | 31.1119 | 20261014-022543_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.5770 | 0.9295 | 0.6244 | 2.2207 | 20261014-022639_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.1448 | 0.9840 | 0.1745 | 0.0299 | 20261014-022811_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261014-022814_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261014-022818_identity |  |
