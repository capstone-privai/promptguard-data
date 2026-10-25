# 세션 템플릿

`sessions.jsonl`과 같은 모양의 파일에서 비밀값 자리에 placeholder를 쓰면, `dataset_build.py`가 결정적 합성값으로 채운다. 이때 넣은 위치를 그대로 gold로 기록한다.

```bash
python metric-detection/scripts/dataset_build.py --template metric-detection/templates/example.jsonl --origin authored
# -> metric-detection/data_test/sessions_from_example.jsonl, metric-detection/data_answer/gold_from_example.jsonl
# --name N 을 주면 sessions_N.jsonl, gold_N.jsonl 로 쓴다
python metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_example.jsonl
```

## `--origin`: 필수, 파일 단위

| origin | 언제 | allowed_use |
|---|---|---|
| `authored` | 비밀이 그 맥락에 자연스럽게 있도록 직접 쓴 세션 | rule_eval, ml_eval, ml_train |
| `injected` | 원래 비밀용으로 쓰지 않은 궤적(공개 에이전트 로그 등)에 placeholder를 끼워 넣은 세션 | **rule_eval만** |

`injected` 데이터는 비밀과 주변 맥락이 맞지 않는다. ML 필터가 이 데이터로 학습하면 비밀이 아니라 "끼워 넣은 흔적"을 배운다. 그래서 규칙기반 검출기 평가에만 쓴다. CredSweeper의 ML 검증을 켠 평가는 `ml_eval`이므로 `injected`에서는 허용하지 않는다. 한 파일에는 한 origin만 둔다. `meta.origin`과 `meta.allowed_use`는 빌더가 채우며, verify는 [dataset_policy.py](../scripts/dataset_policy.py)의 표와 다르면 실패한다. 데이터를 쓰는 쪽은 `require_use(sessions, "ml_train")`처럼 용도를 확인한 뒤 써야 한다.

## 파일 형식

한 줄에 세션 하나.

```json
{"session_id": "tpl-01", "meta": {"scenario": "..."},
 "items": [{"turn_id": "t0", "channel": "tool_output", "text": "DB_PASSWORD={{password:db}}\n"}]}
```

- `session_id`, `items` 필수. `meta`는 선택이며 `group_id`(기본값 session_id)와 자유 필드를 넣을 수 있다.
- item: `channel`, `text` 필수. `turn_id`(기본값 `t0`), `item_id`(넣는다면 0부터 순서대로)는 선택.
- channel: `prompt`(사용자 메시지), `instructions`(시스템 프롬프트에 들어가는 지침), `tool_input`(모델이 쓴 도구 인자, 예: 셸 명령), `tool_output`(도구 결과. 셸 명령의 stdout과 stderr는 구분하지 않고 한 텍스트로 담는다). 자세한 정의는 [metric-detection README](../README.md#형식)에 있다.

## placeholder

| 문법 | 뜻 |
|---|---|
| `{{kind:name}}` | 생성값. 같은 세션에서 `kind:name`이 같으면 같은 값(반복 노출) |
| `{{kind}}` | 이름 없음. 나올 때마다 새 값 |
| `{{kind:name\|transform}}` | 생성값을 변환한 표면 문자열 전체를 gold로 표시 |
| `{{TYPE=literal}}` | 고정 문자열을 TYPE으로 라벨. 예: `{{PASSWORD=changeme}}` |
| `\{{` | 글자 그대로의 `{{` |

| kind | gold type | 모양 |
|---|---|---|
| `password` | PASSWORD | 14자, 대소문자·숫자·기호 포함 |
| `token` | TOKEN | 영숫자 40자 |
| `github_token` | TOKEN | `ghp_` + 36자 |
| `slack_token` | TOKEN | `xoxb-…` |
| `jwt` | TOKEN | HS256 JWT |
| `api_key` | SECRET | 영숫자 40자 |
| `secret` | SECRET | 영숫자 48자 |
| `hex_secret` | SECRET | 소문자 hex 64자 |
| `uuid_key` | SECRET | UUID v4 모양의 키 |
| `aws_access_key` | ACCESS_KEY | `AKIA` + 16자 |
| `aws_secret_key` | SECRET | 40자 (`/+` 포함) |
| `publishable_key` | ACCESS_KEY | `pk_test_` + 24자 |
| `db_uri` | PASSWORD | `postgresql://service:<pw>@db.example.invalid:5432/app`의 `<pw>` 부분만 (URL 속 자격증명은 비밀번호만 정답, [LABELING.md](../LABELING.md)). `url` 변환만 쓸 수 있다 |
| `private_key` | PRIVATE_KEY | Ed25519 PKCS#8 PEM (BEGIN/END 포함) |

| transform | 결과 |
|---|---|
| `base64` | base64 인코딩 (type 유지) |
| `url` | 퍼센트 인코딩 (type 유지) |
| `json` | JSON 문자열 안의 표현(개행은 `\n`) (type 유지). 예: 서비스 계정 JSON의 PEM |
| `basic=user` | `base64("user:값")`, type은 TOKEN |

변환은 왼쪽부터 차례로 적용한다. 예: `{{password:db|url|base64}}`.

빈칸이 없는 `{{Abc…}}`처럼 placeholder와 비슷하지만 해석되지 않는 문자열은 오타로 보고 빌드를 멈춘다. Helm의 `{{ .Values.x }}`, GitHub Actions의 `${{ secrets.X }}`처럼 공백이 있는 형태는 그대로 둔다.

값은 `VERSION:템플릿파일명:session_id:kind:name`에서 결정적으로 만든다. 따라서 템플릿이 같으면 매번 같은 결과가 나오고, verify의 재생성 검사로 확인할 수 있다. 공개된 규칙으로 만든 값이라 실제 인증에 쓰면 안 된다.


## ML 학습용 템플릿 (`ml_train_build.py`)

학습용 합성 데이터([계획](../docs/README_ml-train-plan.md))는 평가용 생성기와 따로 [ml_train_build.py](../scripts/ml_train_build.py)로 만들고 검증한다. 위 문법과 kind를 모두 쓸 수 있고, 아래가 더해진다. 모든 세션은 `authored`다.

```bash
python metric-detection/scripts/ml_train_build.py build metric-detection/templates/ml_train/T.jsonl        # 만들기
python metric-detection/scripts/ml_train_build.py verify metric-detection/data_test/sessions_ml_T.jsonl     # 검증 (따로 실행)
python metric-detection/scripts/ml_train_build.py report metric-detection/data_test/sessions_ml_T.jsonl     # 값 모양 통계 (scikit-learn 필요)
# -> data_test/sessions_ml_T.jsonl, data_answer/gold_ml_T.jsonl, labels_ml_T.jsonl (어려운 음성의 위치와 kind, 값은 없음)
```

| 더해진 것 | 뜻 |
|---|---|
| kind | [value_gen.py](../scripts/value_gen.py)의 `SECRET_KINDS`: `password_mix`, `password_random`, `password_human`, `password_weak`, `passphrase`, `generic_secret`, `generic_token`, `jwt_any`, `aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`, `gcp_api_key`, `azure_storage_key`, `digitalocean_token`, `cloudflare_token`, `github_classic`, `github_oauth`, `github_app`, `github_fine_grained`, `gitlab_pat`, `npm_token`, `pypi_token`, `dockerhub_pat`, `huggingface_token`, `slack_bot`, `slack_user`, `slack_webhook`, `discord_webhook`, `sendgrid_key`, `twilio_auth_token`, `twilio_api_key`, `stripe_secret`, `stripe_publishable`, `openai_key`, `anthropic_key`, `datadog_api_key`, `shopify_token`, `postman_key`, `mapbox_public`, `private_key_any`, `rsa_private_key`, `ec_private_key`, `openssh_private_key`. 여기에 비밀 출처 카탈로그의 서비스 형식 351개(`anthropic_admin_key`, `sourcegraph_cody_token`, `wireguard_private_key` 등)가 더해진다. 목록과 형식은 [value_gen_catalog.py](../scripts/value_gen_catalog.py)에 있고, [ml_train_catalog.py](../scripts/ml_train_catalog.py)가 만든다 |
| `{{neg:KIND}}` | 정답이 아닌 값. 나올 때마다 새 값이고 labels 파일에 위치와 KIND를 남긴다. KIND: `redaction`, `template`, `reference`, `code`, `doc_example`, `descriptor`, `empty`, `hash`, `identifier`, `non_credential`, `setting`, `public_key`, `pem_header`, 그리고 카탈로그 대조군용 `prefix_redaction`, `prefix_example`, `prefix_template`, `secret_ref`, `wallet_address`, `public_key_raw`, `template_ko`, `auth_setting` |
| `{{neg:prefix_redaction\|of=KIND}}` | `prefix_*` 세 종은 비밀 kind를 받아 그 접두사를 남긴다(`ghp_xxxx…`, `sk-ant-api03-EXAMPLE`, `glpat-YOUR_TOKEN_HERE`). label_rules가 각각 redaction, doc_example, template으로 읽는다. 접두사가 없는 kind에는 쓸 수 없다 |
| `{{mask:NAME}}` | tool_input에만 쓴다. 앞에서 나온 비밀 NAME(`{{password:s1}}`의 `s1`, `{{PASSWORD=postgres}}`의 `postgres`)을 PromptGuard Mod가 에이전트에게 보여 주는 모양 `[KIND_n]`으로 바꾼다. KIND는 탐지기 type(`value_gen.mask_kind`), n은 type별로 세션에서 처음 나온 순서다. labels 파일에 `mask`로 남고 정답이 아니다. 학습 데이터의 tool_input에는 비밀값이 들어가지 않는다 |
| `\|wrap=N` | N자마다 줄바꿈을 넣는다(터미널 폭). 줄바꿈을 포함한 span 하나가 정답이다 |
| `\|truncate=N` | 개인키 블록을 BEGIN 줄과 본문 N줄만 남기고 자른다(N ≥ 1) |
| `meta.split` (필수) | `train`, `val`, `test`, `test_ood`. 값 시드에 들어가므로 split마다 값이 다르다. 같은 `group_id`는 한 split에만 둔다 |
| `meta.variants` | 세션을 N번 만든다. `session_id~0` … `~N-1`, 값만 다르다 |
| `meta.value_profile` | `mltrain`이면 기본 kind(`password`, `token`, `api_key`, `secret`, `hex_secret`, `db_uri` 등)를 여러 모양의 계열에서 뽑는다(`value_gen.PROFILE`). 비밀번호는 무작위 35%, 사람이 지은 값 30%, 약한·흔한 값 20%, 패스프레이즈 10%, hex·base64 5% |

- 값은 `VERSION:split:템플릿파일명:session_id[~k]:kind:name`에서 만든다.
- 넣은 값이 그 자리에서 정답이 될 수 없으면 그 값만 다시 뽑는다(최대 8번). 다시 뽑는 경우는 셋이다.
  - 흔한 값이 자격증명 자리 밖에 놓였다. 흔한 값이 나오지 않는 계열에서 다시 뽑는다.
  - label_rules가 값을 제외 kind로 읽는다.
  - 따옴표 없는 자리에서 값이 `.`으로 끝나는 것처럼, 경계 규칙에 맞지 않는다.
- `verify`가 보는 것은 다섯 가지다.
  - `dataset_verify.py`의 스키마와 LABELING.md 검사
  - 정답 자리 검사: 식별자 자리의 정답, 자격증명 자리 밖의 흔한 정답이 없어야 한다. 걸리면 템플릿을 고친다.
  - tool_input에 정답이 없고, mask는 tool_input 안의 `[KIND_n]`인지
  - `neg:` 값이 label_rules에서도 정답이 아닌 kind로 읽히는지
  - split 누수: group이 한 split에만 있고, 고유한 정답 값이 두 split에 함께 나오지 않는지
  - sessions, gold, labels 세 파일의 재생성 바이트 일치
