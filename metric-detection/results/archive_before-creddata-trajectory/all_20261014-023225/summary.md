# metric-detection 전체 평가

## sessions.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.5625 | 0.9130 | 0.6093 | 13.2450 | 20261014-023225_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.2812 | 1.0000 | 0.3285 | 0.0000 | 20261014-023225_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.5938 | 0.9565 | 0.6425 | 6.6225 | 20261014-023225_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.6875 | 0.9000 | 0.7216 | 19.8675 | 20261014-023228_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.5312 | 1.0000 | 0.5862 | 0.0000 | 20261014-023228_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.2188 | 1.0000 | 0.2593 | 0.0000 | 20261014-023230_promptguard_unanimous |  |

## sessions_2.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.6667 | 0.8448 | 0.6960 | 14.2180 | 20261014-023232_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.4583 | 1.0000 | 0.5140 | 0.0000 | 20261014-023232_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.6528 | 0.8621 | 0.6861 | 11.0585 | 20261014-023234_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.7083 | 0.7826 | 0.7220 | 22.1169 | 20261014-023234_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.6389 | 0.9400 | 0.6826 | 3.1596 | 20261014-023236_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.4167 | 1.0000 | 0.4717 | 0.0000 | 20261014-023238_promptguard_unanimous |  |

## sessions_from_CredData.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.4418 | 0.2726 | 0.3930 | 68.2279 | 20261014-023241_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.3639 | 0.7800 | 0.4074 | 5.7943 | 20261014-023243_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.2973 | 0.1995 | 0.2707 | 75.5346 | 20261014-023245_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.6621 | 0.2009 | 0.4538 | 116.9785 | 20261014-023602_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.3017 | 0.3758 | 0.3141 | 31.3875 | 20261014-023759_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.1397 | 0.9831 | 0.1687 | 0.2488 | 20261014-025137_promptguard_unanimous |  |

## sessions_from_Nemotron-PII.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.2051 | 0.6329 | 0.2372 | 2.9784 | 20261014-025907_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.0931 | 0.6278 | 0.1122 | 1.1894 | 20261014-025918_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.1705 | 0.7026 | 0.2009 | 1.8651 | 20261014-025918_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.2312 | 0.6228 | 0.2645 | 3.3019 | 20261014-025921_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.1754 | 0.6947 | 0.2062 | 1.6462 | 20261014-030304_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.0551 | 0.6416 | 0.0674 | 1.0848 | 20261014-030320_promptguard_unanimous |  |

## sessions_from_SWE-Gym.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 1.0000 | 0.0025 | 0.0124 | 1.5018 | 20261014-030702_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 1.0000 | 0.1111 | 0.3846 | 0.0303 | 20261014-030718_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 1.0000 | 0.0012 | 0.0059 | 3.1624 | 20261014-030731_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 1.0000 | 0.0011 | 0.0056 | 3.3440 | 20261014-030735_promptguard_any |  |
| promptguard | consensus=majority | ok | 1.0000 | 0.0029 | 0.0142 | 1.3164 | 20261014-031135_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 1.0000 | 0.5000 | 0.8333 | 0.0038 | 20261014-031252_promptguard_unanimous |  |

## sessions_from_example.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.7000 | 1.0000 | 0.7447 | 0.0000 | 20261014-031339_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.8000 | 1.0000 | 0.8333 | 0.0000 | 20261014-031341_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.6000 | 1.0000 | 0.6522 | 0.0000 | 20261014-031343_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.9000 | 1.0000 | 0.9184 | 0.0000 | 20261014-031344_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.7000 | 1.0000 | 0.7447 | 0.0000 | 20261014-031346_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.5000 | 1.0000 | 0.5556 | 0.0000 | 20261014-031348_promptguard_unanimous |  |

## sessions_from_noseyparker.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.6610 | 0.7810 | 0.6819 | 53.5211 | 20261014-031349_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.6011 | 0.8115 | 0.6340 | 38.4977 | 20261014-031352_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.5926 | 0.6941 | 0.6104 | 81.6901 | 20261014-031411_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.7977 | 0.6884 | 0.7732 | 107.9812 | 20261014-031413_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.6239 | 0.7492 | 0.6455 | 57.2770 | 20261014-031434_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.4217 | 0.9308 | 0.4734 | 6.5728 | 20261014-031455_promptguard_unanimous |  |

## sessions_from_openhands-feedback.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.9778 | 0.0913 | 0.3323 | 1.5401 | 20261014-031516_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.1111 | 0.7143 | 0.1337 | 0.0070 | 20261014-031532_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.8667 | 0.0578 | 0.2281 | 2.2414 | 20261014-031742_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.9778 | 0.0487 | 0.2030 | 3.0273 | 20261014-031746_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.8889 | 0.1600 | 0.4651 | 0.7366 | 20261014-031856_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.0444 | 0.6667 | 0.0546 | 0.0000 | 20261014-031913_promptguard_unanimous |  |

## sessions_from_privesc-llm-data.jsonl

| system | config | status | recall | precision | f2 | fp_per_1k_lines | run_dir | note |
|---|---|---|---|---|---|---|---|---|
| promptguard | detectors=credsweeper | ok | 0.9627 | 0.2024 | 0.5496 | 192.9895 | 20261014-032148_promptguard_credsweeper |  |
| promptguard | detectors=gitleaks | ok | 0.2540 | 0.9914 | 0.2984 | 0.0224 | 20261014-032232_promptguard_gitleaks |  |
| promptguard | detectors=promptguard-rules | ok | 0.9231 | 0.6238 | 0.8423 | 27.9566 | 20261014-032255_promptguard_promptguard-rules |  |
| promptguard | consensus=any | ok | 0.9553 | 0.1955 | 0.5375 | 199.5544 | 20261014-032303_promptguard_any |  |
| promptguard | consensus=majority | ok | 0.9415 | 0.8397 | 0.9192 | 8.6808 | 20261014-032311_promptguard_majority |  |
| promptguard | consensus=unanimous | ok | 0.2321 | 0.9987 | 0.2742 | 0.0150 | 20261014-035718_promptguard_unanimous |  |

## PromptGuard 탐지기 구성별

행은 시스템 앙상블에서 투표하는 어댑터와 합의 규칙이다. 합의 규칙을 적지 않은 행은 시스템 설정(detector.json)의 규칙을 따르고, 어댑터를 적지 않은 행은 설정된 어댑터 전부가 투표한다.

### recall

| 구성 | sessions | sessions_2 | sessions_from_CredData | sessions_from_Nemotron-PII | sessions_from_SWE-Gym | sessions_from_example | sessions_from_noseyparker | sessions_from_openhands-feedback | sessions_from_privesc-llm-data |
|---|---|---|---|---|---|---|---|---|---|
| credsweeper 단독 | 0.562 | 0.667 | 0.442 | 0.205 | 1.000 | 0.700 | 0.661 | 0.978 | 0.963 |
| gitleaks 단독 | 0.281 | 0.458 | 0.364 | 0.093 | 1.000 | 0.800 | 0.601 | 0.111 | 0.254 |
| promptguard-rules 단독 | 0.594 | 0.653 | 0.297 | 0.170 | 1.000 | 0.600 | 0.593 | 0.867 | 0.923 |
| 전체, any | 0.688 | 0.708 | 0.662 | 0.231 | 1.000 | 0.900 | 0.798 | 0.978 | 0.955 |
| 전체, majority | 0.531 | 0.639 | 0.302 | 0.175 | 1.000 | 0.700 | 0.624 | 0.889 | 0.942 |
| 전체, unanimous | 0.219 | 0.417 | 0.140 | 0.055 | 1.000 | 0.500 | 0.422 | 0.044 | 0.232 |

### precision

| 구성 | sessions | sessions_2 | sessions_from_CredData | sessions_from_Nemotron-PII | sessions_from_SWE-Gym | sessions_from_example | sessions_from_noseyparker | sessions_from_openhands-feedback | sessions_from_privesc-llm-data |
|---|---|---|---|---|---|---|---|---|---|
| credsweeper 단독 | 0.913 | 0.845 | 0.273 | 0.633 | 0.003 | 1.000 | 0.781 | 0.091 | 0.202 |
| gitleaks 단독 | 1.000 | 1.000 | 0.780 | 0.628 | 0.111 | 1.000 | 0.812 | 0.714 | 0.991 |
| promptguard-rules 단독 | 0.957 | 0.862 | 0.199 | 0.703 | 0.001 | 1.000 | 0.694 | 0.058 | 0.624 |
| 전체, any | 0.900 | 0.783 | 0.201 | 0.623 | 0.001 | 1.000 | 0.688 | 0.049 | 0.196 |
| 전체, majority | 1.000 | 0.940 | 0.376 | 0.695 | 0.003 | 1.000 | 0.749 | 0.160 | 0.840 |
| 전체, unanimous | 1.000 | 1.000 | 0.983 | 0.642 | 0.500 | 1.000 | 0.931 | 0.667 | 0.999 |

### F2

| 구성 | sessions | sessions_2 | sessions_from_CredData | sessions_from_Nemotron-PII | sessions_from_SWE-Gym | sessions_from_example | sessions_from_noseyparker | sessions_from_openhands-feedback | sessions_from_privesc-llm-data |
|---|---|---|---|---|---|---|---|---|---|
| credsweeper 단독 | 0.609 | 0.696 | 0.393 | 0.237 | 0.012 | 0.745 | 0.682 | 0.332 | 0.550 |
| gitleaks 단독 | 0.328 | 0.514 | 0.407 | 0.112 | 0.385 | 0.833 | 0.634 | 0.134 | 0.298 |
| promptguard-rules 단독 | 0.642 | 0.686 | 0.271 | 0.201 | 0.006 | 0.652 | 0.610 | 0.228 | 0.842 |
| 전체, any | 0.722 | 0.722 | 0.454 | 0.265 | 0.006 | 0.918 | 0.773 | 0.203 | 0.538 |
| 전체, majority | 0.586 | 0.683 | 0.314 | 0.206 | 0.014 | 0.745 | 0.646 | 0.465 | 0.919 |
| 전체, unanimous | 0.259 | 0.472 | 0.169 | 0.067 | 0.833 | 0.556 | 0.473 | 0.055 | 0.274 |

### 1,000줄당 과잉 마스킹

| 구성 | sessions | sessions_2 | sessions_from_CredData | sessions_from_Nemotron-PII | sessions_from_SWE-Gym | sessions_from_example | sessions_from_noseyparker | sessions_from_openhands-feedback | sessions_from_privesc-llm-data |
|---|---|---|---|---|---|---|---|---|---|
| credsweeper 단독 | 13.25 | 14.22 | 68.23 | 2.98 | 1.50 | 0.00 | 53.52 | 1.54 | 192.99 |
| gitleaks 단독 | 0.00 | 0.00 | 5.79 | 1.19 | 0.03 | 0.00 | 38.50 | 0.01 | 0.02 |
| promptguard-rules 단독 | 6.62 | 11.06 | 75.53 | 1.87 | 3.16 | 0.00 | 81.69 | 2.24 | 27.96 |
| 전체, any | 19.87 | 22.12 | 116.98 | 3.30 | 3.34 | 0.00 | 107.98 | 3.03 | 199.55 |
| 전체, majority | 0.00 | 3.16 | 31.39 | 1.65 | 1.32 | 0.00 | 57.28 | 0.74 | 8.68 |
| 전체, unanimous | 0.00 | 0.00 | 0.25 | 1.08 | 0.00 | 0.00 | 6.57 | 0.00 | 0.01 |
