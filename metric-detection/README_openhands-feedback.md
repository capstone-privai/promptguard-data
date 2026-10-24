# openhands-feedback 변환본

[all-hands/openhands-feedback](https://huggingface.co/datasets/all-hands/openhands-feedback)를 우리 세션 형식으로 바꾼 데이터다. OpenHands 사용자들이 피드백 버튼을 누르며 **공개로 공유한 실제 세션 275개**다. 과제가 정해져 있지 않다: 게임 만들기, 웹 스크래핑, 저장소 수정, 웹 브라우징, 패키지 설치 등 사용자가 시킨 일이 그대로 들어 있다. 기존 데이터에 없던 **실제 사용자와 에이전트가 주고받은 트래픽**을 시험한다.

업스트림이 공개 전에 민감정보를 검토해 지웠다고 밝혔고, 실제로 토큰 자리에 `ghp_-XXX`, `sk--XXX` 같은 흔적이 남아 있다. 그래서 정답은 161개(값 23종, 세션 13개)뿐이고 **대부분 음성인 데이터**다. 주로 실제 에이전트 트래픽에서의 과잉 마스킹을 재는 데 쓴다.

외부 데이터이므로 `meta.origin`은 `external`, `allowed_use`는 `["rule_eval", "ml_eval"]`이다. 원본 라이선스는 MIT다. 변환 결과는 git에 올리지 않고 아래 순서대로 다시 만든다. 정답 판정은 [reviews/openhands-feedback.jsonl](reviews/openhands-feedback.jsonl)에 값 없이 남아 있다.

## 다시 만들기

`facf45600d625510b98222ec584a8c9ac59272a2` 리비전 기준(약 114MB). 변환에는 `pyarrow`가 필요하다.

```bash
# 1. 받기
hf download all-hands/openhands-feedback --repo-type dataset \
  --revision facf45600d625510b98222ec584a8c9ac59272a2 --local-dir ../openhands-feedback

# 2. 변환과 검증 (이 저장소 루트에서). 정답은 metric-detection/reviews/openhands-feedback.jsonl에서 읽는다
python metric-detection/scripts/convert_openhands_feedback.py --openhands ../openhands-feedback
python metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_openhands-feedback.jsonl --openhands ../openhands-feedback
```

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_openhands-feedback.jsonl` | 공유된 세션 하나가 세션 하나 (약 21MB) |
| `data_answer/gold_from_openhands-feedback.jsonl` | 정답 span |
| `labels_from_openhands-feedback.jsonl` | 검토한 후보 값의 모든 등장 위치와 판정, 이유. 값은 들어 있지 않다 |

세션 275개, item 12,526개, 정답 span 161개(PASSWORD 69 / SECRET 53 / TOKEN 38 / PRIVATE_KEY 1). 정답이 있는 세션은 13개다.

| channel | item | 정답 span |
|---|---|---|
| `prompt` | 1,103 | 1 |
| `tool_input` | 5,778 | 80 |
| `tool_output` | 5,645 | 80 |

`tool_input`의 정답 80개(에이전트가 `write`/`edit`로 쓴 코드와 테스트 안의 값)는 데이터에 그대로 두지만 채점하지 않는다. 모델이 직접 쓴 도구 인자라 가릴 대상이 아니기 때문이다([채점 기준](README.md#단위)). 채점하는 정답은 `prompt`와 `tool_output`의 81개(SECRET 46 / PASSWORD 26 / TOKEN 8 / PRIVATE_KEY 1)다.

## 변환 규칙

### 채널

| OpenHands 이벤트 | channel |
|---|---|
| 사용자 메시지 (`source: user`, `action: message`) | `prompt` |
| 에이전트 동작의 인자: `run`의 명령, `run_ipython`의 코드, `browse_interactive`의 브라우저 동작, `read`의 경로, `write`/`edit`로 쓰는 파일 내용 | `tool_input` |
| 그 동작에 대한 관찰: 명령 출력, IPython 출력, 페이지 텍스트, 파일 내용, edit diff, 오류 | `tool_output` |

- 에이전트의 일반 메시지는 채널이 없어 뺐다(privesc와 같다). 상태 변경, 계획, 환경 초기화(`initialize`, 원본에서 `LLM_API_KEY`가 비어 있다)도 뺐다.
- `turn_id`는 사용자 메시지 순번이다.
- item이 30,000자보다 길면 앞 30,000자만 둔다. Claude Code가 도구 결과를 자르는 길이와 같다. 긴 명령 출력(최대 5MB)과 웹 페이지 때문이다.
- 브라우저 관찰의 스크린샷(base64)과 접근성 트리 같은 extras는 넣지 않았다.

### 정답

라벨이 없는 데이터라 CredSweeper, gitleaks, 정규식으로 후보 475개를 모으고 하나씩 판정했다. 방법과 판정 기준은 [reviews/README.md](reviews/README.md)에 있다. 정답 값의 다른 등장 위치는 [LABELING.md](LABELING.md)의 퍼뜨림 기준을 따른다.

| 세션 | type | 값의 정체 | 정답 span |
|---|---|---|---|
| openhands-189 | SECRET | Django `startproject`가 만든 `SECRET_KEY` | 36 |
| openhands-161 | PASSWORD, SECRET | 에이전트가 쓴 앱과 테스트의 비밀번호 리터럴(`cat123`, `testpassword`, `wrong_password`, `opensesame`)과 하드코딩한 Fernet 키 | 65 |
| openhands-144, 145, 150, 152 | TOKEN | 테스트 코드의 `GITHUB_TOKEN`/`mockToken` 값 `mock-token`, `mock_token` | 36 |
| openhands-164~166 | SECRET | `api_key="test_api_key"`, `LLM_API_KEY="sk_test_12345"` | 10 |
| openhands-101 | SECRET | Flask `app.secret_key = 'supersecretkey'` | 5 |
| openhands-120 | PASSWORD, TOKEN | 피드백 제출의 비밀번호와 JWT | 3 |
| openhands-098 | PASSWORD | 에이전트가 만든 비밀번호 생성기가 사용자에게 출력한 비밀번호 | 1 |
| openhands-221 | PRIVATE_KEY, PASSWORD | OWASP Juice Shop 소스에 하드코딩된 RSA 개인키와 계정 비밀번호 4개 | 5 |

### 정답에서 뺀 것 (labels 파일에만 기록)

판정한 값 475개 중 452개는 자격증명이 아니다. 이유별 개수:

| 이유 | 값 |
|---|---|
| 어느 등장 위치도 자격증명 자리가 아닌 짧은 값 | 145 |
| 코드, 이름, URL, 경로, 식별자 | 104 |
| 변수·속성 참조 (`$GITHUB_TOKEN`, `os.environ.get(`) | 83 |
| placeholder, 가린 흔적 (`ghp_-XXX`, `<your_token_here>`, `YOUR_OPENAI_API_KEY`) | 52 |
| 이름이나 단어 하나 | 42 |
| 숫자, 버전 | 20 |
| 그 밖 (SSH 호스트키 지문, 탐지기 경계가 어긋난 일부) | 6 |

2026-10-24에 길이와 모양으로 자동 판정했던 음성 중, 등장 위치 하나라도 자격증명 자리 규칙(`label_rules.classify`)에 걸리는 값을 모두 다시 봤고 13개를 정답으로 바꿨다.

## LABELING.md를 이 데이터에 적용한 점

| 결정 | 근거 |
|---|---|
| 테스트·개발용 값도 자격증명 자리에 있으면 정답 (`testpassword`, `mock-token`, `test_api_key`, Django 개발용 `SECRET_KEY`) | 값의 강도나 테스트용인지는 보지 않는다 |
| placeholder와 업스트림이 가린 흔적은 정답이 아님 | LABELING.md `redaction`, `template` |
| 같은 값의 다른 등장 위치는 퍼뜨림 기준을 따른다 | LABELING.md |

## 기준 시스템 점수

아래 점수는 2026-10-24 정답 기준 통일(LABELING.md) 전의 정답으로 잰 것이다. 다시 재야 한다.

`metric-detection/results/all_20261014-021351`(2026-10-14, 정확 일치 채점. CredSweeper 1.19.0, gitleaks 8.30.1, PromptGuard `promptguard-claude-demoV0@8973016`의 탐지기 앙상블). 세 시스템 모두 채점하는 세 채널(`prompt`, `instructions`, `tool_output`)을 검사한다. `tool_input`의 정답 2개, edit, 줄 60,313줄은 채점하지 않는다.

| 시스템 | recall | precision | F2 | 1,000줄당 과잉 마스킹 |
|---|---|---|---|---|
| PromptGuard | 0.889 | 0.160 | 0.465 | 0.74 |
| CredSweeper ml=off | 0.978 | 0.190 | 0.535 | 0.66 |
| CredSweeper ml=on | 0.978 | 0.603 | 0.870 | 0.10 |
| gitleaks | 0.111 | 0.714 | 0.134 | 0.007 |

- **recall은 상한값이다.** 정답 후보를 CredSweeper와 gitleaks가 냈으므로, 이 둘이 놓친 자격증명은 정답에 들어갈 수 없다(정규식으로 일부 보충). 이 데이터의 recall을 다른 데이터와 비교하지 않는다.
- **precision과 과잉 마스킹이 이 데이터의 핵심 수치다.** 실제 사용자 세션 28만 줄(채점하는 세 채널)에서 CredSweeper(ML off)는 1,000줄에 0.66번, ML on은 0.10번 비밀이 아닌 것을 가린다. CredData의 과잉 마스킹(어렵게 고른 음성)과 달리 실제 트래픽의 비율이다. 어떤 규칙이 무엇을 가렸는지와 gitleaks가 놓친 이유는 [새 외부 소스로 본 기존 시스템의 약점](docs/README_baseline-new-sources.md)에 있다.

## 알려진 한계

- **업스트림이 민감정보를 지운 데이터다.** 원래 세션에 있던 실제 비밀 대부분이 이미 빠져 있다. 남은 정답 10종은 공개해도 되는 값이거나(Juice Shop, 데모 코드) 업스트림이 놓친 값이다.
- **정답은 후보 생성기와 한 명의 판정에 기댄다** ([reviews/README.md](reviews/README.md#한계)).
- **OpenHands 이벤트 형식이다.** 도구 인자를 OpenHands가 기록한 형태로 옮겼다. Claude Code의 도구 호출 형식과 다르다.
- 세션 수는 275개뿐이고 일부 세션이 매우 길다(최대 수천 item).
