# SWE-Gym 변환본

[SWE-Gym/OpenHands-SFT-Trajectories](https://huggingface.co/datasets/SWE-Gym/OpenHands-SFT-Trajectories)를 우리 세션 형식으로 바꾼 데이터다. OpenHands 에이전트가 실제 파이썬 저장소(moto, MONAI, pandas, dask, mypy, conan, pydantic 등)의 GitHub 이슈를 고친 **성공 궤적 491개**다. 코딩 에이전트의 전형적인 트래픽(소스 파일 보기, 테스트 실행, 수정, 재현 스크립트)을 그대로 담고 있다.

자격증명을 심은 실행이 아니므로 정답은 2개뿐이고 **거의 전부 음성인 데이터**다. moto(AWS 모의 라이브러리, 155개)처럼 테스트용 가짜 키와 비밀번호가 많은 저장소가 들어 있어, 탐지기가 **실제 코딩 에이전트 트래픽에서 얼마나 자주 잘못 가리는지**를 재기에 좋다.

외부 데이터이므로 `meta.origin`은 `external`, `allowed_use`는 `["rule_eval", "ml_eval"]`이다. 원본 라이선스는 MIT다. 변환 결과는 git에 올리지 않고 아래 순서대로 다시 만든다. 정답 판정은 [reviews/SWE-Gym.jsonl](reviews/SWE-Gym.jsonl)에 값 없이 남아 있다.

## 다시 만들기

`4aaa5a4a4b5861f4799d2336908760c190ac3b17` 리비전 기준(약 10MB). 변환에는 `pyarrow`가 필요하다.

```bash
# 1. 받기
hf download SWE-Gym/OpenHands-SFT-Trajectories --repo-type dataset \
  --revision 4aaa5a4a4b5861f4799d2336908760c190ac3b17 --local-dir ../SWE-Gym-OpenHands-SFT-Trajectories

# 2. 변환과 검증 (이 저장소 루트에서). 정답은 metric-detection/reviews/SWE-Gym.jsonl에서 읽는다
python metric-detection/scripts/convert_swe_gym.py --swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories
python metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_SWE-Gym.jsonl --swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories
```

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_SWE-Gym.jsonl` | 궤적 하나가 세션 하나 (약 32MB) |
| `data_answer/gold_from_SWE-Gym.jsonl` | 정답 span |
| `labels_from_SWE-Gym.jsonl` | 검토한 후보 값의 모든 등장 위치와 판정, 이유. 값은 들어 있지 않다 |

세션 491개, item 18,900개, 약 60만 줄, 정답 span 58개(PASSWORD 46 / SECRET 9 / TOKEN 3, 세션 15개). 채점하는 정답은 `tool_input`을 뺀 27개(PASSWORD 20 / SECRET 4 / TOKEN 3)다.

| channel | item | 정답 span |
|---|---|---|
| `instructions` | 491 | 0 |
| `prompt` | 1,331 | 4 |
| `tool_input` | 8,779 | 31 |
| `tool_output` | 8,299 | 23 |

## 변환 규칙

### 채널

| 원본 메시지 | channel |
|---|---|
| `system` (도구 설명이 든 시스템 프롬프트, 모든 궤적에서 같다) | `instructions` |
| 첫 `user` (업로드한 저장소와 이슈 설명), 하네스의 "Please continue working on the task" 재촉 | `prompt` |
| `assistant`가 쓴 함수 호출 그대로 (`<function=execute_bash><parameter=command>…</parameter></function>`) | `tool_input` (호출 하나가 item 하나) |
| `EXECUTION RESULT of [...]`로 시작하는 `user` 메시지 | `tool_output` |

- assistant의 일반 글은 채널이 없어 뺐다(privesc와 같다).
- `turn_id`는 assistant 메시지 순번이다. 도구 결과는 그 호출을 낸 turn을 따른다.
- item이 30,000자보다 길면 앞 30,000자만 둔다.

### 정답

라벨이 없는 데이터라 후보 852개를 모아 판정했다. 방법과 기준은 [reviews/README.md](reviews/README.md)에 있다. 정답 값의 다른 등장 위치는 [LABELING.md](LABELING.md)의 퍼뜨림 기준을 따른다.

| 판정 | 값 | 내용 |
|---|---|---|
| credential | 23 | moto 테스트와 재현 스크립트에서 비밀번호·키 자리에 넣은 리터럴(`Password='Password123!'`, `TemporaryPassword='TempP@ssw0rd!'`, `MasterUserPassword="test123456789"`, `SecretString='test-value'`, `aws_secret_access_key='fake'` 등 21개), moto의 가짜 Cognito가 발급한 AccessToken과 IdToken(`swe-gym-251`) |
| not_credential | 829 | 아래 표 |

| 이유 | 값 |
|---|---|
| 이름이나 단어 하나 | 240 |
| 코드 표현식 (`kwargs.get(`, `Optional[str`) | 194 |
| 어느 등장 위치도 자격증명 자리가 아닌 짧은 값 | 118 |
| 변수·속성 참조 | 102 |
| 비밀 자리가 아닌 UUID (AWS request id, 리소스 id) | 89 |
| 코드, 이름, 식별자, 옵션 (사람 판정) | 41 |
| 리소스 이름(ARN), 이메일, 경로 | 16 |
| 숫자, 버전 | 12 |
| 시크릿 이름, 기기 푸시 토큰 (`test-secret`, SNS의 `test-token`) | 9 |
| 해시 (dask `tokenize()` 출력) | 4 |
| placeholder | 4 |

2026-10-24에 길이와 모양으로 자동 판정했던 음성 중, 등장 위치 하나라도 자격증명 자리 규칙(`label_rules.classify`)에 걸리는 값을 모두 다시 봤고 21개를 정답으로 바꿨다.

## LABELING.md를 이 데이터에 적용한 점

| 결정 | 근거 |
|---|---|
| 테스트 비밀번호(`Password123!`, `P@ssw0rd!`, `TempPass123!`)도 자격증명 자리에 있으면 정답 | 값의 강도나 테스트용인지는 보지 않는다 |
| moto 가짜 Cognito의 JWT는 정답 | 인증 자리의 JWT |
| request id로 쓰인 UUID, `ClientToken`(중복 요청 방지 값), 페이지네이션 토큰은 정답이 아님 | LABELING.md `identifier` |
| enum 상수(`REFRESH_TOKEN = "REFRESH_TOKEN"`, `AWS_SECRET_ACCESS_KEY = 'AWS_SECRET_ACCESS_KEY'`)는 정답이 아님 | 값이 아니라 이름이다 |
| 해시는 정답이 아님 | LABELING.md `hash` |

## 기준 시스템 점수

아래 점수는 2026-10-24 정답 기준 통일(LABELING.md) 전의 정답으로 잰 것이다. 다시 재야 한다.

`metric-detection/results/all_20261014-021351`(2026-10-14, 정확 일치 채점. CredSweeper 1.19.0, gitleaks 8.30.1, PromptGuard `promptguard-claude-demoV0@8973016`의 탐지기 앙상블). 세 시스템 모두 채점하는 세 채널(`prompt`, `instructions`, `tool_output`)을 검사한다. `tool_input`(정답 없음)의 edit와 줄 75,990줄은 채점하지 않는다.

| 시스템 | recall | precision | 1,000줄당 과잉 마스킹 | 과잉 마스킹 수 |
|---|---|---|---|---|
| PromptGuard | 1.000 | 0.003 | 1.32 | 696 |
| CredSweeper ml=off | 1.000 | 0.003 | 1.16 | 611 |
| CredSweeper ml=on | 1.000 | 0.008 | 0.49 | 258 |
| gitleaks | 1.000 | 0.111 | 0.03 | 16 |

정답이 2개뿐이라 recall과 precision은 의미가 적다. **1,000줄당 과잉 마스킹을 본다.** 코딩 에이전트가 오픈소스 저장소를 고치는 동안, CredSweeper(ML off)는 1,000줄마다 약 1.2번 비밀이 아닌 것(코드 표현식, request id, 테스트 값)을 가린다. metric-task에서 본 것처럼 이런 과잉 마스킹은 과제에 필요한 값을 가려 작업을 막을 수 있다. 어떤 규칙이 무엇을 가렸는지는 [새 외부 소스로 본 기존 시스템의 약점](docs/README_baseline-new-sources.md#6-키워드-규칙이-코드-조각을-값으로-잡음)에 있다.

## 알려진 한계

- **성공한 궤적만 있다.** 원본이 SFT용으로 성공 궤적만 공개했다.
- **정답은 후보 생성기와 한 명의 판정에 기댄다** ([reviews/README.md](reviews/README.md#한계)). 후보로 잡히지 않은 자격증명이 있으면 그것을 가린 것은 과잉 마스킹으로 센다.
- **시스템 프롬프트가 491번 반복된다.** `instructions` 채널 item이 모두 같은 글이다.
- OpenHands(CodeAct)의 XML식 함수 호출 형식이다. Claude Code의 도구 호출 형식과 다르다.
