# 세션 템플릿

`sessions.jsonl`과 같은 모양의 파일에서 비밀값 자리에 placeholder를 쓰면, `build_dataset.py`가 결정적 합성값으로 채운다. 이때 넣은 위치를 그대로 gold로 기록한다.

```bash
python metric-1/scripts/build_dataset.py --template metric-1/templates/example.jsonl --origin authored
# -> metric-1/sessions_from_example.jsonl, metric-1/gold_from_example.jsonl
python metric-1/scripts/verify_dataset.py metric-1/sessions_from_example.jsonl
```

## `--origin`: 필수, 파일 단위

| origin | 언제 | allowed_use |
|---|---|---|
| `authored` | 비밀이 그 맥락에 자연스럽게 있도록 직접 쓴 세션 | rule_eval, ml_eval, ml_train |
| `injected` | 원래 비밀용으로 쓰지 않은 궤적(공개 에이전트 로그 등)에 placeholder를 끼워 넣은 세션 | **rule_eval만** |

`injected` 데이터는 비밀과 주변 맥락이 맞지 않는다. ML 필터가 이 데이터로 학습하면 비밀이 아니라 "끼워 넣은 흔적"을 배운다. 그래서 규칙기반 검출기 평가에만 쓴다. 한 파일에는 한 origin만 둔다. `meta.origin`과 `meta.allowed_use`는 빌더가 채우며, verify는 [dataset_policy.py](../scripts/dataset_policy.py)의 표와 다르면 실패한다. 데이터를 쓰는 쪽은 `require_use(sessions, "ml_train")`처럼 용도를 확인한 뒤 써야 한다.

## 파일 형식

한 줄에 세션 하나.

```json
{"session_id": "tpl-01", "meta": {"scenario": "..."},
 "items": [{"turn_id": "t0", "channel": "tool_output", "text": "DB_PASSWORD={{password:db}}\n"}]}
```

- `session_id`, `items` 필수. `meta`는 선택이며 `group_id`(기본값 session_id)와 자유 필드를 넣을 수 있다.
- item: `channel`, `text` 필수. `turn_id`(기본값 `t0`), `item_id`(넣는다면 0부터 순서대로)는 선택.
- channel: `prompt`(사용자 메시지), `instructions`(AGENTS.md 등), `tool_input`(모델이 쓴 도구 인자, 예: bash 명령), `tool_output`(도구 결과. bash는 stdout과 stderr가 합쳐져 나온다).

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
| `aws_access_key` | ACCESS_KEY | `AKIA` + 16자 |
| `aws_secret_key` | SECRET | 40자 (`/+` 포함) |
| `publishable_key` | ACCESS_KEY | `pk_test_` + 24자 |
| `db_uri` | SECRET | `postgresql://service:<pw>@db.example.invalid:5432/app` 전체 |
| `private_key` | PRIVATE_KEY | Ed25519 PKCS#8 PEM (BEGIN/END 포함) |

| transform | 결과 |
|---|---|
| `base64` | base64 인코딩 (type 유지) |
| `url` | 퍼센트 인코딩 (type 유지) |
| `basic=user` | `base64("user:값")`, type은 TOKEN |

변환은 왼쪽부터 차례로 적용한다. 예: `{{password:db|url|base64}}`.

빈칸이 없는 `{{Abc…}}`처럼 placeholder와 비슷하지만 해석되지 않는 문자열은 오타로 보고 빌드를 멈춘다. Helm의 `{{ .Values.x }}`, GitHub Actions의 `${{ secrets.X }}`처럼 공백이 있는 형태는 그대로 둔다.

값은 `VERSION:템플릿파일명:session_id:kind:name`에서 결정적으로 만든다. 따라서 템플릿이 같으면 매번 같은 결과가 나오고, verify의 재생성 검사로 확인할 수 있다. 공개된 규칙으로 만든 값이라 실제 인증에 쓰면 안 된다.
