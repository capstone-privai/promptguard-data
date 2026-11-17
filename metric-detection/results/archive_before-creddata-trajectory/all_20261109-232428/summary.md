# metric-detection 전체 평가

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7500 | 0.9000 | 0.7759 | 19.8675 | 20261109-232429_promptguard |  |
| credsweeper | ml=off | ok | 0.6875 | 0.6471 | 0.6790 | 72.8477 | 20261109-232429_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6562 | 0.8077 | 0.6818 | 33.1126 | 20261109-232431_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.3125 | 1.0000 | 0.3623 | 0.0000 | 20261109-232436_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261109-232436_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261109-232436_identity |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7361 | 0.7826 | 0.7450 | 22.1169 | 20261109-232437_promptguard |  |
| credsweeper | ml=off | ok | 0.7083 | 0.7429 | 0.7150 | 25.2765 | 20261109-232505_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6528 | 0.8000 | 0.6777 | 15.7978 | 20261109-232507_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.4722 | 1.0000 | 0.5280 | 0.0000 | 20261109-232513_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261109-232513_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261109-232513_identity |  |

## sessions_from_CredData.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7622 | 0.1859 | 0.4705 | 147.6726 | 20261109-232513_promptguard |  |
| credsweeper | ml=off | ok | 0.7500 | 0.3289 | 0.5971 | 34.7114 | 20261109-232543_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6600 | 0.7231 | 0.6717 | 5.6778 | 20261109-232836_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.3975 | 0.8296 | 0.4437 | 1.8260 | 20261109-235107_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261109-235114_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261109-235121_identity |  |

## sessions_from_Nemotron-PII.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.2428 | 0.6365 | 0.2771 | 3.2413 | 20261109-235123_promptguard |  |
| credsweeper | ml=off | ok | 0.2585 | 0.5519 | 0.2892 | 5.7464 | 20261110-005956_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.1914 | 0.6697 | 0.2233 | 3.0118 | 20261110-010011_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.0710 | 0.5711 | 0.0861 | 1.1952 | 20261110-010130_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-010131_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-010132_identity |  |

## sessions_from_SWE-Gym.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 1.0000 | 0.0143 | 0.0677 | 3.6466 | 20261110-010133_promptguard |  |
| credsweeper | ml=off | ok | 0.6429 | 0.0294 | 0.1241 | 1.1254 | 20261110-024247_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.1429 | 0.0154 | 0.0538 | 0.4842 | 20261110-024329_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.2143 | 0.3333 | 0.2308 | 0.0227 | 20261110-024426_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-024427_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-024428_identity |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-024428_promptguard |  |
| credsweeper | ml=off | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-024437_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 | 20261110-024438_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 | 20261110-024442_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-024442_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-024442_identity |  |

## sessions_from_noseyparker.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7761 | 0.7852 | 0.7779 | 69.4836 | 20261110-024442_promptguard |  |
| credsweeper | ml=off | ok | 0.7114 | 0.7766 | 0.7236 | 77.9343 | 20261110-025026_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6368 | 0.8589 | 0.6715 | 38.4977 | 20261110-025030_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.5473 | 0.8871 | 0.5927 | 16.9014 | 20261110-025046_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-025046_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-025046_identity |  |

## sessions_from_openhands-feedback.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.8791 | 0.0653 | 0.2516 | 4.0352 | 20261110-025046_promptguard |  |
| credsweeper | ml=off | ok | 0.6154 | 0.2424 | 0.4706 | 0.6132 | 20261110-035803_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.5055 | 0.6301 | 0.5263 | 0.0952 | 20261110-035828_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.0549 | 0.7143 | 0.0674 | 0.0070 | 20261110-035903_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-035904_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-035904_identity |  |

## sessions_from_trajectory.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.8217 | 0.6357 | 0.7763 | 7.6731 | 20261110-035905_promptguard |  |
| credsweeper | ml=off | ok | 0.8251 | 0.5738 | 0.7587 | 9.7175 | 20261110-040444_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.8251 | 0.8651 | 0.8328 | 2.0178 | 20261110-040452_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.5993 | 0.9861 | 0.6503 | 0.1328 | 20261110-040518_gitleaks |  |
| oracle |  | ok | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 20261110-040518_oracle |  |
| identity |  | ok | 0.0000 |  |  | 0.0000 | 20261110-040519_identity |  |
