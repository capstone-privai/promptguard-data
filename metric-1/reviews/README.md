# 검토로 만든 정답

라벨이 없는 외부 데이터(공개된 에이전트 궤적)는 자격증명 후보를 모아 하나씩 판정해 정답을 만든다. 이 폴더의 파일이 그 판정이다. 변환기(`convert_openhands_feedback.py`, `convert_swe_gym.py`)가 이 파일을 읽어 판정이 `credential`인 값을 정답으로 바꾼다.

| 파일 | 데이터 | 판정한 값 | credential | 설명 |
|---|---|---|---|---|
| `openhands-feedback.jsonl` | [README_openhands-feedback.md](../README_openhands-feedback.md) | 475 | 10 | 규칙 352, 사람 123 |
| `SWE-Gym.jsonl` | [README_SWE-Gym.md](../README_SWE-Gym.md) | 852 | 2 | 규칙 787, 사람 65 |

## 파일 형식

한 줄에 판정 하나. **값은 들어 있지 않다.** 값은 `where`가 가리키는 위치에서 변환기가 다시 읽고, `sha256`으로 같은 값인지 확인한다.

```json
{"sha256": "9af14ab0…", "where": ["openhands-120", 12, 97, 113], "length": 16, "type": "PASSWORD",
 "verdict": "credential", "reason": "password of the feedback submission, used to delete it later",
 "reviewed_by": "manual", "found_by": ["credsweeper_ml-off_all", "gitleaks", "regex:key_value"], "sessions": ["openhands-120"]}
```

- `where`: 그 값이 나오는 한 곳 (session_id, item_id, start, end). 변환 규칙이 바뀌어 위치가 어긋나면 변환기가 멈춘다. 그때는 아래 순서로 다시 검토한다.
- `verdict`: `credential` 또는 `not_credential`. `credential`이면 같은 세션 안의 모든 등장 위치가 정답이다.
- `reviewed_by`: `rule`(아래 규칙으로 정해짐) 또는 `manual`(사람이 판단).
- `found_by`: 그 값을 후보로 낸 탐지기와 정규식.

## 만드는 순서

```bash
# 1. 세션 만들기 (정답 없이; 리뷰 파일이 없으면 정답 0개)
python metric-1/scripts/convert_swe_gym.py --swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories
# 2. 후보를 낼 탐지기 실행 (모든 채널)
python metric-1/scripts/run_gitleaks.py --sessions metric-1/data_test/sessions_from_SWE-Gym.jsonl --channels all
python metric-1/scripts/evaluate.py run --system gitleaks --findings metric-1/results/gitleaks/sessions_from_SWE-Gym.jsonl \
    --sessions metric-1/data_test/sessions_from_SWE-Gym.jsonl --out metric-1/results/review
python metric-1/scripts/evaluate.py run --system credsweeper --ml off --channels all \
    --sessions metric-1/data_test/sessions_from_SWE-Gym.jsonl --out metric-1/results/review
# 3. 후보 모으기: 탐지기 결과 + 정규식, 기계적인 판정은 미리 채움 (값이 든 작업 파일은 metric-1/results/ 아래에만)
python metric-1/scripts/review_candidates.py collect metric-1/data_test/sessions_from_SWE-Gym.jsonl \
    --runs metric-1/results/review/<credsweeper 실행 폴더> metric-1/results/review/<gitleaks 실행 폴더> --out metric-1/results/review/SWE-Gym.worksheet.jsonl
# 4. 작업 파일에서 verdict가 비어 있는 행을 판정한다 (verdict, reason, credential이면 type)
# 5. 값 없이 기록
python metric-1/scripts/review_candidates.py apply metric-1/results/review/SWE-Gym.worksheet.jsonl --out metric-1/reviews/SWE-Gym.jsonl
# 6. 정답을 넣어 다시 변환
python metric-1/scripts/convert_swe_gym.py --swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories
```

후보 정규식(`review_candidates.py`의 `REGEXES`)은 키워드 대입(`password=…`, `"token": …`), `Bearer`/`Basic` 헤더, URL 속 자격증명(`://user:pw@`), 명령줄 비밀번호(`-p…`, `--password`, `sshpass -p`), 서비스 접두어(`ghp_`, `sk-`, `sk_live_`, `xoxb-`, `AKIA`, `AIza`, `hf_`, `glpat-`, `npm_` …), JWT, PEM 개인키다. CredSweeper와 gitleaks가 놓치는 자리(위치 인자, 자연어)를 보충하려는 것이다.

## 판정 기준

[지표 1의 정답 정의](../README.md#정답의-정의)를 따르고, 정의가 갈리는 곳은 기존 외부 데이터(CredData, privesc-llm-data)와 같게 정했다.

### 규칙으로 정하는 것 (`reviewed_by: rule`, 모두 `not_credential`)

| 규칙 | 예 | 근거 |
|---|---|---|
| placeholder, 가린 흔적 | `ghp_-XXX`, `sk--XXX`, `<your_token_here>`, `YOUR_GITHUB_TOKEN`, `your-secret-key-change-this-in-production` | 정의의 placeholder, CredData의 X |
| 변수·속성 참조 | `$GITHUB_TOKEN`, `os.environ.get(`, `self.api_key`, `{token}` | 정의의 변수 참조 |
| 숫자, 버전, 시간 형식 | `4096`, `^22.0.1`, `2022-11-28` | 비밀이 아님 |
| 9자 미만 | `cat123`, `admin123` | privesc와 CredData가 짧은 값을 정답에서 뺀 기준 |
| 이름이나 단어 하나 | `opensesame`, `testpassword`, `supersecretkey`, `mock_token`, `sk_test_12345` | 사전 단어, 테스트용 가짜 값. CredData가 F로 두는 값 |
| 코드 표현식 | `kwargs.get(`, `Optional[str`, `generate_password_hash(` | 비밀이 아님 |
| 비밀 자리가 아닌 UUID | `'RequestId': '523e…'` | 정의의 UUID, request id. 앞 60자에 secret/token/key/password 같은 말이 있으면 규칙으로 정하지 않고 사람이 본다 |
| 리소스 이름, 이메일, 경로 | `arn:aws:…`, `monai.contact@gmail.com`, `/workspace/…` | 비밀이 아님 |

### 사람이 판단하는 것 (`reviewed_by: manual`)

| 판정 | 기준 | 예 |
|---|---|---|
| credential | 무작위 문자열 모양이고 그 자리에서 실제로 인증에 쓰이는 값. 테스트·개발용이어도 동작하면 정답 (privesc가 테스트 환경에 심은 값을 정답으로 둔 것과 같다) | Django `SECRET_KEY`, 코드의 Fernet 키, 공개 앱(OWASP Juice Shop) 소스에 하드코딩된 계정 비밀번호와 RSA 개인키, moto 가짜 Cognito가 발급한 JWT, 피드백 제출의 비밀번호와 토큰 |
| not_credential | 흔한 패턴의 테스트 비밀번호 | `Password123!`, `P@ssw0rd!`, `TempPass123!` (CredData의 F, privesc의 흔한 비밀번호와 같다) |
| not_credential | 해시, 공개 정보 | dask `tokenize()` 해시, SSH 호스트키 지문 |
| not_credential | 탐지기 경계가 어긋난 일부 | 다른 행에서 판정한 값의 앞부분만 잡은 후보 |

## 한계

- **후보 생성기가 하나도 못 찾은 자격증명은 정답에 없다.** 그래서 이 데이터들에서 CredSweeper와 gitleaks의 recall은 실제보다 높게 나온다(후보를 낸 쪽이 그 탐지기다). 이 데이터는 주로 **실제 에이전트 트래픽에서의 과잉 마스킹**(precision, 1,000줄당 과잉 마스킹)을 보는 데 쓴다.
- 사람 판정은 한 사람(이 작업을 한 에이전트)이 했고 교차 검토는 없다. 판정과 이유가 모두 파일에 남아 있으니 다르게 볼 값은 `verdict`를 고쳐 다시 변환하면 된다.
