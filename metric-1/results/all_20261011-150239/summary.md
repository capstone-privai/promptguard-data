# 지표 1 전체 평가

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.5625 | 0.9130 | 0.6093 | 13.2450 | 20261011-150240_promptguard |  |
| credsweeper | ml=off | ok | 0.6562 | 0.6765 | 0.6602 | 72.8477 | 20261011-150240_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.5938 | 0.8077 | 0.6270 | 33.1126 | 20261011-150240_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.3125 | 1.0000 | 0.3623 | 0.0000 | 20261011-150240_gitleaks |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.6667 | 0.8596 | 0.6980 | 12.6382 | 20261011-150241_promptguard |  |
| credsweeper | ml=off | ok | 0.7083 | 0.7714 | 0.7201 | 25.2765 | 20261011-150241_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.6528 | 0.8333 | 0.6823 | 15.7978 | 20261011-150241_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.4722 | 1.0000 | 0.5280 | 0.0000 | 20261011-150241_gitleaks |  |

## sessions_from_CredData.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.4448 | 0.6595 | 0.4758 | 13.2399 | 20261011-150242_promptguard |  |
| credsweeper | ml=off | ok | 0.9773 | 0.3962 | 0.7557 | 31.3717 | 20261011-150242_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.9711 | 0.9828 | 0.9735 | 0.3573 | 20261011-150242_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.4334 | 0.8491 | 0.4804 | 1.6341 | 20261011-150317_gitleaks |  |

## sessions_from_Nemotron-PII.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.2144 | 0.7462 | 0.2501 | 2.6834 | 20261011-150321_promptguard |  |
| credsweeper | ml=off | failed |  |  |  |  | 20261011-150329_credsweeper_ml-off | exit -6: libc++abi: terminating due to uncaught exception of type std::__1::system_error: recursive_mutex lock failed: Invalid argument |
| credsweeper | ml=on | ok | 0.2121 | 0.7193 | 0.2469 | 3.0450 | 20261011-150340_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.0975 | 0.7570 | 0.1181 | 1.1514 | 20261011-150428_gitleaks |  |

## sessions_from_SWE-Gym.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 1.0000 | 0.0108 | 0.0518 | 0.3461 | 20261011-150430_promptguard |  |
| credsweeper | ml=off | ok | 1.0000 | 0.0033 | 0.0161 | 1.1556 | 20261011-150447_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 1.0000 | 0.0077 | 0.0373 | 0.4880 | 20261011-150500_credsweeper_ml-on |  |
| gitleaks |  | ok | 1.0000 | 0.1111 | 0.3846 | 0.0303 | 20261011-150518_gitleaks |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.7000 | 1.0000 | 0.7447 | 0.0000 | 20261011-150520_promptguard |  |
| credsweeper | ml=off | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 | 20261011-150521_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 | 20261011-150523_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 | 20261011-150525_gitleaks |  |

## sessions_from_noseyparker.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.6866 | 0.8239 | 0.7103 | 49.7653 | 20261011-150527_promptguard |  |
| credsweeper | ml=off | ok | 0.7892 | 0.7487 | 0.7807 | 92.9577 | 20261011-150529_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.7265 | 0.8464 | 0.7477 | 46.0094 | 20261011-150532_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.6268 | 0.8871 | 0.6659 | 26.2911 | 20261011-150534_gitleaks |  |

## sessions_from_openhands-feedback.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 1.0000 | 0.2195 | 0.5844 | 0.5639 | 20261011-150535_promptguard |  |
| credsweeper | ml=off | ok | 1.0000 | 0.1948 | 0.5474 | 0.6555 | 20261011-150603_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.9778 | 0.6027 | 0.8696 | 0.1022 | 20261011-150624_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.1111 | 0.7143 | 0.1337 | 0.0070 | 20261011-150637_gitleaks |  |

## sessions_from_privesc-llm-data.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard |  | ok | 0.5814 | 0.5128 | 0.5663 | 28.1136 | 20261011-150641_promptguard |  |
| credsweeper | ml=off | ok | 0.5842 | 0.4886 | 0.5622 | 31.1119 | 20261011-150655_credsweeper_ml-off |  |
| credsweeper | ml=on | ok | 0.5772 | 0.9297 | 0.6245 | 2.2207 | 20261011-150713_credsweeper_ml-on |  |
| gitleaks |  | ok | 0.1465 | 0.9960 | 0.1767 | 0.0299 | 20261011-150833_gitleaks |  |
