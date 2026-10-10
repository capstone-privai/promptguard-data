# 지표 1: 탐지·마스킹 성능

코딩 에이전트가 주고받는 텍스트에서 비밀값을 얼마나 정확히 찾아 가리는지를 span 단위로 채점한다. 데이터는 특정 에이전트에 묶이지 않는 형식으로 만든다. 지금 데이터는 합성 파일럿 v0.1이며 사람 검토를 기다린다.

평가 대상 시스템(PromptGuard)은 [promptguard-claude-demoV0](https://github.com/capstone-privai/promptguard-claude-demoV0)에 있고, 채점기가 그 체크아웃의 CredSweeper worker를 불러 쓰고 Claude Code Mod의 치환 규칙을 따른다.

## 폴더

| 경로 | 내용 |
|---|---|
| `data_test/` | 평가기 입력(세션). 정답은 들어 있지 않다 |
| `data_answer/` | 정답 span(gold) |
| `scripts/` | 생성(`dataset_build.py`, `convert_*.py`), 검증(`dataset_verify.py`), 용도 정책(`dataset_policy.py`), 채점(`evaluate.py`), 전체 조합 채점(`run_all.py`), gitleaks 탐지(`run_gitleaks.py`), 후보 검토(`review_candidates.py`) |
| [`evaluation/`](evaluation/README.md) | 채점기: 시스템 어댑터, span 채점, 지표 집계, 결과 파일 |
| `templates/` | placeholder로 세션을 쓰는 템플릿과 [작성법](templates/README.md) |
| [`README_CredData.md`](README_CredData.md) | CredData 변환 방법, 변환 규칙, 우리 라벨 기준과 다른 점 |
| [`README_privesc-llm-data.md`](README_privesc-llm-data.md) | privesc-llm-data 변환 방법, 채널 대응, 자동 정답 규칙, 한계 |
| [`../docs/README_baseline-recall.md`](../docs/README_baseline-recall.md) | 기존 시스템(CredSweeper, gitleaks)과 PromptGuard 데모의 recall이 낮은 이유 분석 (합성 데이터, CredData, privesc-llm-data) |
| [`../docs/README_baseline-new-sources.md`](../docs/README_baseline-new-sources.md) | 새 외부 소스 4개로 본 기존 시스템의 약점: 문장·문서 서식 속 비밀, 서비스별 토큰 형식, 실제 에이전트 트래픽의 과잉 마스킹 |
| [`README_Nemotron-PII.md`](README_Nemotron-PII.md), [`README_openhands-feedback.md`](README_openhands-feedback.md), [`README_SWE-Gym.md`](README_SWE-Gym.md), [`README_noseyparker.md`](README_noseyparker.md) | 2026-10-08에 더한 외부 소스 4개의 변환 방법, 정답 규칙, 기존 데이터와 맞춘 점, 기준 점수 |
| [`reviews/`](reviews/README.md) | 라벨이 없는 소스(openhands-feedback, SWE-Gym)의 정답 판정. 값 없이 해시와 위치만 둔다 |

## 데이터셋

| 데이터셋 | 입력 (`data_test/`) | 정답 (`data_answer/`) | 세션 | item | gold span | origin | 설명 |
|---|---|---|---|---|---|---|---|
| 내장 코퍼스 | `sessions.jsonl` | `gold.jsonl` | 12 | 51 | 32 | authored | `dataset_build.py`에 직접 쓴 합성 세션이다. 환경 파일, 트레이스백, HTTP 헤더, git 이력, Kubernetes Secret, PEM 키, 비밀이 없는 음성 예시 등 12개 상황을 담았다. |
| 템플릿 예시 | `sessions_from_example.jsonl` | `gold_from_example.jsonl` | 2 | 9 | 10 | authored | [templates/example.jsonl](templates/example.jsonl)의 placeholder를 채워 만든 세션이다. |
| 에이전트 세션 v2 | `sessions_2.jsonl` | `gold_2.jsonl` | 43 | 152 | 78 | authored | [templates/agent_sessions_2.jsonl](templates/agent_sessions_2.jsonl)로 만든 세션이다. 설정 파일 읽기, 명령 출력, 로그, 에이전트가 쓴 명령(`tool_input`), 자연어 속 비밀, 약한·테스트 비밀번호, 비밀 없는 고엔트로피 출력의 7개 범주(`meta.category`)로 나뉜다. `python metric-1/scripts/dataset_build.py --template metric-1/templates/agent_sessions_2.jsonl --origin authored --name 2`로 다시 만든다. |
| CredData | `sessions_from_CredData.jsonl` | `gold_from_CredData.jsonl` | 11,030 | 25,345 | 15,596 | external | [Samsung CredData](https://github.com/Samsung/CredData)의 파일 조각을 세션 형식으로 바꾼 것이다. **평가 전용이며 학습에 쓰지 않는다.** 파일 본문은 원본 저장소의 라이선스를 따르므로 git에 올리지 않고 각자 다시 만든다([README_CredData.md](README_CredData.md)). |
| privesc-llm-data | `sessions_from_privesc-llm-data.jsonl` | `gold_from_privesc-llm-data.jsonl` | 2,200 | 122,286 | 10,624 | recorded | [sailab-vienna/privesc-llm-data](https://huggingface.co/datasets/sailab-vienna/privesc-llm-data)의 리눅스 권한 상승 에이전트 궤적을 세션 형식으로 바꾼 것이다. 실행 전에 환경에 심어 둔 비밀번호와 SSH 키를 원본 metadata에서 가져와, 텍스트에서 그 위치를 찾아 정답을 자동으로 만든다. 정답 유형은 PASSWORD와 PRIVATE_KEY뿐이다. 용량 때문에 git에 올리지 않고 각자 다시 만든다([README_privesc-llm-data.md](README_privesc-llm-data.md)). |
| Nemotron-PII | `sessions_from_Nemotron-PII.jsonl` | `gold_from_Nemotron-PII.jsonl` | 6,000 | 6,000 | 3,866 | external | [nvidia/Nemotron-PII](https://huggingface.co/datasets/nvidia/Nemotron-PII)의 합성 업무 문서(설정 파일, API 문서, 비밀번호 안내 메일, 양식 등). `password`, `api_key`, 인증 쿠키 값을 정답으로 쓴다. 정답 있는 문서와 없는 문서가 3,000개씩이고, 비정형 문서는 `prompt`(사용자가 붙여 넣은 글), 정형 문서는 `tool_output`에 둔다([README_Nemotron-PII.md](README_Nemotron-PII.md)). |
| openhands-feedback | `sessions_from_openhands-feedback.jsonl` | `gold_from_openhands-feedback.jsonl` | 275 | 12,526 | 47 | external | [all-hands/openhands-feedback](https://huggingface.co/datasets/all-hands/openhands-feedback)의 실제 사용자 세션. 업스트림이 민감정보를 지워 거의 음성이다. 정답은 후보를 검토해 정했다([README_openhands-feedback.md](README_openhands-feedback.md), [reviews/](reviews/README.md)). |
| SWE-Gym | `sessions_from_SWE-Gym.jsonl` | `gold_from_SWE-Gym.jsonl` | 491 | 18,900 | 2 | external | [SWE-Gym/OpenHands-SFT-Trajectories](https://huggingface.co/datasets/SWE-Gym/OpenHands-SFT-Trajectories)의 코딩 에이전트 궤적(moto, MONAI, pandas …). 실제 코딩 트래픽의 과잉 마스킹을 재는 음성 데이터다([README_SWE-Gym.md](README_SWE-Gym.md)). |
| Nosey Parker | `sessions_from_noseyparker.jsonl` | `gold_from_noseyparker.jsonl` | 573 | 573 | 351 | external | [Nosey Parker](https://github.com/praetorian-inc/noseyparker) 내장 규칙 189개의 예시와 음성 예시. 수백 종 서비스의 토큰 형식을 시험한다([README_noseyparker.md](README_noseyparker.md)). |

합성 데이터의 비밀값은 모두 결정적으로 만든 가짜 값이다. 정답은 탐지기 결과와 상관없이, 값을 끼워 넣는 순간에 위치를 기록해 만든다.

`data_test/`와 `data_answer/`는 git에 올리지 않는다(`.gitignore`). 저장소를 받은 뒤 [생성과 검증](#생성과-검증)의 명령으로 각자 만든다. 합성 데이터도 올리지 않는 이유는, 비밀값이 실제 형식(예: AWS 키 ID와 시크릿 키 쌍)을 따르는 가짜 값이라 GitHub push protection이 진짜 비밀로 보고 push를 막기 때문이다. 생성은 결정적이므로 누가 만들어도 바이트 단위로 같은 파일이 나온다.

### 검토했지만 쓰지 않은 소스

| 소스 | 이유 |
|---|---|
| [ai4privacy/pii-masking-400k](https://huggingface.co/datasets/ai4privacy/pii-masking-400k) | 6개 언어의 짧은 글에 PASSWORD 라벨이 있지만, 라이선스가 학술 목적이라도 파생물 생성에 서면 허가를 요구한다 |
| [SecretBench](https://github.com/setu1421/SecretBench) | 사람이 검증한 비밀 15,084개지만, 저자에게 연락해 데이터 보호 계약을 맺어야 BigQuery 접근 권한을 준다 |
| SWE-rebench, SWE-smith, Nemotron-SWE 궤적 | 수 GB~11GB라 노트북 용량에 비해 크다. 같은 성격의 SWE-Gym(10MB)을 대신 썼다 |

## 형식

데이터는 세션 → item → span의 세 층이다. 세션 하나는 `session_id`, `items`, `meta`로 이루어진다. item은 에이전트와 오간 텍스트 한 덩어리다.

```json
{"session_id": "m1-01-node-env",
 "items": [{"item_id": 0, "turn_id": "t0", "channel": "prompt", "text": "로컬 API가 인증 오류로 ..."},
           {"item_id": 1, "turn_id": "t0", "channel": "tool_output", "text": "NODE_ENV=development\n..."}],
 "meta": {"origin": "authored", "allowed_use": ["rule_eval", "ml_eval", "ml_train"], "...": "..."}}
```

`channel`은 그 텍스트가 모델의 입출력에서 어느 자리에 놓이는지 나타낸다.

| channel | 내용 |
|---|---|
| `prompt` | 사용자 메시지 |
| `instructions` | 시스템 프롬프트에 들어가는 지침 (저장소의 에이전트 지침 파일, 설정에 적은 지시문 등) |
| `tool_input` | 모델이 쓴 도구 인자 (예: 셸 명령) |
| `tool_output` | 모델에 돌아가는 도구 결과. 셸 명령의 stdout과 stderr는 구분하지 않고 한 텍스트로 담는다 |

채널은 에이전트와 무관한 구분이다. 에이전트마다 이 네 자리를 어느 지점(훅, 플러그인, 프록시 등)에서 가로채는지는 다르므로, 그 대응은 평가 대상 시스템을 연동하는 쪽에서 정한다.

정답 파일은 한 줄에 span 하나다. span이 없는 item은 정답 파일에 나오지 않는다.

```json
{"session_id": "m1-01-node-env", "item_id": 1, "span_id": 0, "span": {"start": 71, "end": 87, "type": "PASSWORD"}}
```

- `start`, `end`: item `text` 안의 위치. Python 문자열 인덱스(코드 포인트) 기준이며 `end`는 포함하지 않는다.
- `type`: `PASSWORD`, `SECRET`, `TOKEN`, `ACCESS_KEY`, `PRIVATE_KEY` 중 하나.
- 한 item 안의 정답 span은 겹치지 않는다(맞닿는 것은 괜찮다).

## 사용 용도

세션마다 `meta.origin`과 `meta.allowed_use`가 붙는다. 용도 표는 [dataset_policy.py](scripts/dataset_policy.py) 한 곳에만 정의되어 있고, 검증 단계에서 이 표와 다르면 실패한다. 데이터를 쓰는 쪽은 `require_use(sessions, "ml_train")`처럼 용도를 확인한 뒤 쓴다.

| origin | 뜻 | allowed_use |
|---|---|---|
| `authored` | 비밀이 자연스럽게 놓일 맥락에 직접 쓴 세션 | rule_eval, ml_eval, ml_train |
| `recorded` | 미리 비밀을 심어 둔 환경에서 실제로 실행한 에이전트 세션 | rule_eval, ml_eval, ml_train |
| `injected` | 비밀용으로 쓰지 않은 궤적에 비밀을 끼워 넣은 세션 | rule_eval |
| `external` | 외부 벤치마크(CredData) | rule_eval, ml_eval |

`ml_eval`에는 CredSweeper의 ML 검증을 켠 평가(`credsweeper --ml on`)도 포함한다. `injected`는 `rule_eval`만 허용한다.

## 생성과 검증

저장소 루트에서 실행한다.

```bash
# 합성 데이터 (외부 파일 없이 바로 만든다)
python metric-1/scripts/dataset_build.py                       # 내장 코퍼스
python metric-1/scripts/dataset_build.py --template metric-1/templates/example.jsonl --origin authored
python metric-1/scripts/dataset_build.py --template metric-1/templates/agent_sessions_2.jsonl --origin authored --name 2

# 외부 데이터 (원본을 먼저 받는다: 각 README_<소스>.md)
python metric-1/scripts/convert_creddata.py --creddata ../CredData
python metric-1/scripts/convert_privesc.py --privesc ../privesc-llm-data
python metric-1/scripts/convert_nemotron_pii.py --nemotron ../Nemotron-PII                         # pyarrow 필요
python metric-1/scripts/convert_openhands_feedback.py --openhands ../openhands-feedback            # pyarrow 필요
python metric-1/scripts/convert_swe_gym.py --swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories        # pyarrow 필요
python metric-1/scripts/convert_noseyparker.py --noseyparker ../noseyparker

python metric-1/scripts/dataset_verify.py <sessions 파일> [--gold <gold 파일>] [--creddata ../CredData] [--privesc ../privesc-llm-data] \
    [--nemotron ../Nemotron-PII] [--openhands ../openhands-feedback] [--swe-gym ../SWE-Gym-OpenHands-SFT-Trajectories] [--noseyparker ../noseyparker]
```

검증 항목은 스키마, origin과 용도의 일치, span 범위와 겹침, 정답 누락(같은 비밀값이 그 세션의 다른 곳에도 나오는데 정답에서 빠졌는지), 재생성 시 바이트 단위 일치다. 누락 검사는 세션 안에서만 본다. 정답은 세션별 출처에서 나오므로, 같은 사용자명이나 흔한 비밀번호가 아무것도 심지 않은 다른 세션에 나오는 것은 비밀이 아니다.

생성 스크립트는 세션을 `metric-1/data_test/`, 정답을 `metric-1/data_answer/`에 쓰고, 폴더가 없으면 만든다. 채점기의 기본 입력(`data_test/sessions.jsonl`)도 내장 코퍼스를 만들어야 생긴다. 검증 스크립트는 `data_test/sessions*.jsonl`에 짝지어진 `data_answer/gold*.jsonl`을 자동으로 찾는다.

## 정답의 정의

지표 1의 정답 span은 **실제로 인증에 쓰이는 자격증명 값**이다. 과제에 필요한 값인지는 보지 않는다. 과제에 필요해서 남길지(MASK/KEEP)는 [지표 3](../metric-3/README.md)에서 따로 라벨링한다. 이렇게 나누면 탐지기가 규칙 기반이든 ML이든 같은 정답으로 채점하고, ML을 붙여도 정답을 다시 매기지 않는다.

| 경우 | 정답 | 예 |
|---|---|---|
| 실제 값, 또는 실제 값을 같은 모양으로 바꾼 합성·난독화 값 | 자격증명 | API 키, 토큰, CredData T |
| 테스트·개발용이지만 실제로 동작하는 값 | 자격증명 | `x-pack-test-password` |
| 설정에 들어간 기본·약한 비밀번호 | 자격증명 | `DB_PASSWORD=admin` |
| 공개용 키 | 자격증명 | 클라이언트에 넣는 publishable key |
| placeholder, 지운 흔적 | 아님 | `<your-token>`, `YOUR_API_KEY`, `login_and_password_removed`, `***`, `xxxx` |
| 변수 참조 | 아님 | `${TOKEN}`, `os.environ["KEY"]`, 따옴표 없는 식별자 |
| 문서에 나오는 예시 값 | 아님 | `AKIAIOSFODNN7EXAMPLE` |
| 해시, UUID, request id, 이름 | 아님 | 커밋 해시, `x-request-id` |

- 값이 자격증명 자리(예: `Authorization: Basic …`)에 있어도, 값 자체가 placeholder면 정답이 아니다. 규칙 기반 탐지기가 이런 값을 가리면 과잉 마스킹으로 센다. recall은 줄지 않고 precision만 내려간다. ML 검증이 이 과잉 마스킹을 얼마나 줄이는지는 CredSweeper `--ml off`와 `--ml on`을 비교해 본다.
- 이 정의는 시스템이 과제에 필요한 값을 남기는 판단(KEEP)을 하지 않는다고 보고 잰다. KEEP 판단을 켠 시스템은 남긴 자격증명이 놓친 것으로 잡힌다([알려진 한계](evaluation/README.md#알려진-한계)).
- CredData 변환본은 CredData의 T만 정답으로 쓴다. 테스트 값과 약한 비밀번호처럼 이 정의와 어긋나는 부분은 [README_CredData.md](README_CredData.md#정답)에 있다.
- 2026-10-08에 더한 외부 소스 4개(Nemotron-PII, openhands-feedback, SWE-Gym, Nosey Parker)도 CredData, privesc와 같은 기준으로 맞췄다: 9자 미만과 흔한 비밀번호, placeholder, 문서 예시 값, 해시, 식별자는 정답이 아니고, 무작위 모양으로 실제 동작하는 값은 테스트용이어도 정답이며, 같은 값의 모든 등장 위치가 정답이다. 소스별로 정한 것은 각 `README_<소스>.md`의 "기존 두 데이터와 같은 기준으로 맞춘 점"에 있다.

## 채점 기준

### 단위

채점은 item마다 따로 하고, 결과를 데이터셋 전체로 합친다. 한 item에는 두 가지가 있다.

- **정답 span**: 데이터셋이 정한, 그 item에서 가려야 할 비밀값 하나의 위치.
- **edit**: 시스템이 실제로 바꾼 구간 하나. 원문 좌표의 `start`, `end`와 대체 문자열 `replacement`로 이루어진다.

정답은 데이터셋에서만 온다. 시스템이 처리하지 않는 채널에 있는 정답도 분모에 들어가며 놓친 것으로 센다. 현재 PromptGuard는 `prompt`, `instructions`, `tool_output`을 처리하고 모델이 쓴 `tool_input`은 가리지 않으므로, `tool_input`의 정답은 항상 놓친 것이 되고 채널별 recall에 그대로 드러난다.

### 판정

판정은 **span 정확 일치가 아니라 글자 단위로 덮었는지**로 한다.

- **정답 span**: 그 item의 edit들을 합친 구간이 span의 모든 글자를 덮으면 `full`, 일부만 덮으면 `partial`, 한 글자도 덮지 못하면 `missed`다. `full`만 성공이고, `partial`은 비밀값 일부가 노출된 것이므로 실패다.
- **edit**: 정답 span과 한 글자라도 겹치면 참양성, 겹치지 않으면 과잉 마스킹(거짓양성)이다. 정답이 없는 item에서 나온 edit는 모두 과잉 마스킹이다.
- 경계가 정답보다 넓어도 감점하지 않는다. 비밀값을 여러 edit로 나눠 가려도 합쳐서 다 덮으면 `full`이다. edit 하나가 정답 span 둘을 덮으면 두 span 모두 `full`이고, 그 edit는 참양성 하나로 센다.
- 유형(`type`)은 맞히지 않아도 된다. 유형은 유형별 recall 같은 분석에만 쓴다. 대체 문자열의 내용(`[SECRET]`, placeholder 등)도 보지 않는다.

예를 들어 item `DB_PASSWORD=mysecret123`의 정답이 `mysecret123`일 때 다음과 같이 판정한다.

| 시스템이 가린 구간 | 정답 span | edit |
|---|---|---|
| `mysecret123` | `full` | 참양성 |
| `DB_PASSWORD=mysecret123` | `full` (넓게 가려도 성공) | 참양성 |
| `mysecret` | `partial` (`123` 노출, 실패) | 참양성 |
| `DB_PASSWORD` | `missed` | 과잉 마스킹 |
| 없음 | `missed` | 없음 |

정답보다 넓게 가린 정도는 지금 지표에 반영되지 않는다. 정답 밖으로 얼마나 넘쳤는지는 `per_edit.jsonl`의 좌표로 따로 확인해야 한다.

### edit 검증

채점에는 시스템이 보고한 edit만 쓴다. item을 채점하기 전에 edit를 원문에 적용해 보고, 결과가 시스템의 실제 출력과 한 글자라도 다르면 결과를 쓰지 않고 종료 코드 2로 멈춘다. 그래서 시스템이 보고한 edit와 실제 출력이 어긋난 상태로 점수가 나오는 일은 없다. 탐지 후보, 예측, 감사 로그는 채점에 쓰지 않는다.

### 지표

| 지표 | 정의 |
|---|---|
| **recall** (주) | `full` 정답 span / 전체 정답 span |
| **precision** (주) | 정답과 겹치는 edit / 전체 edit |
| F2 | `5PR / (4P + R)`. 비밀을 놓치는 쪽이 더 위험하므로 recall에 가중을 둔다 |
| 1,000줄당 과잉 마스킹 | 정답과 겹치지 않는 edit / 전체 줄 수 × 1000 |
| char recall | 가려진 정답 글자 수 / 전체 정답 글자 수 |
| partial, missed 비율 | `partial` / `missed` 정답 span의 비율 |
| 유형별, 채널별 recall | 정답을 유형, 채널로 나눠 잰 recall |

분모가 0이면 `N/A`다. 지연 시간과 결과 파일의 정확한 정의는 [evaluation/README.md](evaluation/README.md#지표)에 있다.

## 채점 실행

저장소 루트에서 실행한다.

```bash
pip install -r metric-1/evaluation/requirements.txt
python metric-1/scripts/evaluate.py run --system promptguard [--sessions <sessions 파일>] [--system-root ../promptguard-claude-demoV0]
python metric-1/scripts/evaluate.py run --system credsweeper|oracle|identity [--sessions <sessions 파일>]

# gitleaks: 먼저 탐지 결과를 만들고(gitleaks 설치 필요, 예: brew install gitleaks), 그 결과로 채점한다
python metric-1/scripts/run_gitleaks.py --sessions <sessions 파일>
python metric-1/scripts/evaluate.py run --system gitleaks --findings metric-1/results/gitleaks/<sessions 이름>.jsonl --sessions <sessions 파일>
```

결과는 `metric-1/results/<시각>_<system>/`에 쌓인다. 세션의 `meta.allowed_use`에 실행 용도(기본 `rule_eval`, CredSweeper ML 검증이면 `ml_eval`)가 없으면 실행하지 않는다. `oracle`은 recall 1.0, precision 1.0이, `identity`는 recall 0.0, precision `N/A`가 나와야 하므로 채점기 점검용으로 쓴다. 옵션, 채널 대응, 결과 파일은 [evaluation/README.md](evaluation/README.md)에 있다.
