# 손으로 작성한 ML 학습 템플릿

`hand_v1.jsonl`은 160개의 완결된 세션을 각각 직접 작성한 원본이다. 기본 세션에서 문맥을 변형하는 생성 스크립트는 두지 않는다. Python은 JSONL 저장과 검사·집계에만 사용했다. 값 변형은 기존 빌더의 `variants: 5`가 맡는다.

- group 160개: train 128, val 16, test 16. 빌드 후 세션은 640/80/80, 총 800개다.
- id는 모두 `hand-`로 시작한다. meta는 LLM 템플릿과 같은 `split`, `group_id`, `variants`, `value_profile`, `boundary_rule`, `negatives`, `generator` 키를 사용한다. `generator.method`는 `hand_authored`다.
- 비밀은 placeholder 안에만 있다. 흔한 고정값도 `{{PASSWORD=admin}}`처럼 쓴다. tool_input에서 앞서 본 값은 `{{mask:NAME}}`으로만 쓴다.
- 영어·한국어 요청과 env, YAML, JSON, TOML, ini/properties, 코드, HTTP 덤프, 로그, 마크다운 표, PEM 출력을 사용한다. 서비스 형식은 기존 kind와 카탈로그 kind를 함께 쓴다. CSV와 그 예시 열·장면은 사용하지 않았다.
- Jupyter 출력, Terraform state/plan, MCP 결과, 지정된 OOD kind 6개, 공백 패스프레이즈, PuTTY, 환경변수 기본값, Sentry DSN은 넣지 않았다.

경계와 퍼뜨림 목표를 800세션 안에서 함께 충족하려고 세션 하나가 여러 규칙을 다룬다. `boundary_rule`은 주 규칙이며 전체 커버리지 집계의 근거가 아니다. `hand_coverage.md`는 빌드된 gold·labels와 원본 placeholder의 변환 정보로 다시 집계한 결과다. 음성 수는 해당 규칙 세션 안의 모든 비정답 label 위치를 뜻한다. mask는 따로 세며, 규칙 사이 중복이 있다.

## 학습 전용 문법 보완

평가 데이터와 공유하는 LABELING, label_rules, dataset_build, dataset_verify는 수정하지 않았다. 아래 기능은 `ml_train_build.py` 안에만 있다. 기존 placeholder 표기는 그대로 사용할 수 있다.

| 표기/처리 | 용도 |
| --- | --- |
| `{{generic_secret:key\|as=identifier}}` | 같은 `generic_secret:key`의 생성값을 식별자 자리에 다시 쓰되 정답으로 표시하지 않는다 |
| `{{PASSWORD=admin\|as=not_propagated}}` | 흔한 값을 일반 자리에 다시 쓰되 정답으로 표시하지 않는다. 고정 literal에도 두 `as=` 역할을 쓸 수 있다 |
| `{{password_random:pw\|suffix=.}}` | 생성값 끝에 문자를 붙인다. 따옴표 안의 마지막 구두점이 실제 값에 포함되는 사례를 만든다 |
| `{{password_random:pw\|suffix=/@+\|url}}` | 문자를 붙인 뒤 URL 인코딩한다. `suffix`는 뒤따르는 변환보다 먼저 적용된다 |
| 맞닿거나 겹친 gold | 최종 출력에서 span 하나로 병합한다. 더 긴 원래 span의 type을 따르고, PRIVATE_KEY가 있으면 우선한다. 길이가 같으면 앞쪽 type을 유지한다 |

생성값 재등장은 kind, name, 인코딩·suffix가 같아야 같은 표면 문자열이 된다. `as=`만 정답 대신 음성 역할을 지정한다. 빌더는 그 위치를 labels에 `replay: true`와 함께 기록한다. `verify`는 세션에 같은 표면 문자열의 정답이 있는지, 그 재등장 위치를 LABELING이 실제로 `identifier` 또는 `not_propagated`로 읽는지 검사한다. 잘못된 역할로 정답을 숨길 수 없다. tool_input에는 `as=`를 쓸 수 없으며 `mask`를 사용한다.

OpenSSH 개인키의 첫 본문 줄은 형식 머리 부분이 같을 수 있으므로 잘린 OpenSSH 키는 본문을 두 줄 이상 남겼다. 다른 잘린 키도 실제 본문을 포함하고 END 줄은 포함하지 않는다. 비밀번호는 split 사이에 고유값이 겹치지 않도록 무작위·구분자로 이은 패스프레이즈와 흔한 고정값을 조합했다.

## 실행과 검증

저장소 루트에서 실행한다. `report`에는 scikit-learn이 필요하다. 이 작업에서는 기존 `promptguard-demo` Python 환경에 설치된 scikit-learn을 사용했다.

```bash
python metric-detection/scripts/ml_train_build.py build metric-detection/templates/ml_train/hand_v1.jsonl
python metric-detection/scripts/ml_train_build.py verify metric-detection/data_test/sessions_ml_hand_v1.jsonl
python metric-detection/scripts/ml_train_build.py report metric-detection/data_test/sessions_ml_hand_v1.jsonl
python metric-detection/scripts/ml_train_hand_report.py --out metric-detection/templates/ml_train/hand_coverage.md
python metric-detection/scripts/test_ml_train_hand.py
gitleaks dir metric-detection/templates/ml_train/hand_v1.jsonl --no-banner
```

`ml_train_hand_report.py --json`으로 같은 집계를 JSON으로 받을 수 있다. 원본 160개·split 비율·meta·리터럴 비밀·OOD 배제, 3.4절 21개 최소치와 URL 스킴 수를 검사한다. 값과 숫자를 가린 item의 5-token shingle 집합을 split 사이에서 전수 비교하며 Jaccard 0.8 이상이면 실패한다. 160개에는 근사 MinHash 후보 탐색 없이 정확하게 비교할 수 있다. 이 중복 검사는 손 템플릿 내부 범위다. LLM·privesc까지 합친 전체 말뭉치 검사는 내보내기 단계에서 해야 한다.

이번 원본은 build·verify(경계·자리·퍼뜨림·split·바이트 재생성), 규칙별 최소치 검사, 회귀 테스트 13개와 gitleaks를 통과했다. 모양만 보는 로지스틱 회귀의 AUROC는 0.723이다. 유형별 (길이, 문자 구성) 최빈 칸 비율은 ACCESS_KEY 0.200, PASSWORD 0.059, PRIVATE_KEY 0.133, SECRET 0.024, TOKEN 0.067이다. 이 값은 손 템플릿만의 통계다. 전체 학습 말뭉치를 합친 뒤에도 다시 확인해야 한다.

기본 `report`의 `negatives=1460`은 길이가 0인 음성 5곳을 빼고 mask 15곳을 포함한 수다. 커버리지 표는 음성 1,450곳과 mask 15곳을 분리해 센다.

`hand_coverage.md`와 이 문서, 원본 JSONL 및 검사 스크립트는 커밋 대상이다. 빌드된 sessions·gold·labels는 기존 git 제외 경로에만 둔다.
