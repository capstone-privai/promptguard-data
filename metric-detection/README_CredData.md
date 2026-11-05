# CredData 변환본

[Samsung CredData](https://github.com/Samsung/CredData)를 우리 세션 형식으로 바꾼 평가 전용 데이터다. **ML 모델 평가에는 쓸 수 있지만 학습에는 쓰지 않는다.** 세션의 `meta.origin`은 `external`, `allowed_use`는 `["rule_eval", "ml_eval"]`이다.

변환 결과는 git에 올리지 않는다(`.gitignore`). 이 저장소는 공개 저장소인데, CredData도 파일 본문은 배포하지 않고 메타데이터와 다운로드 스크립트만 배포한다. 본문은 각 원본 저장소의 라이선스를 따른다. 아래 순서대로 다시 만든다.

## 다시 만들기

CredData `0b1940e171725ad8937311120b191602608a4801` (2026-09-29) 기준. 이 저장소와 같은 부모 폴더에 둔다.

```bash
# 1. CredData 받기 (macOS: 대소문자 구분 볼륨에서 실행)
#    337개 저장소를 커밋 단위로 받는다. 임시 폴더 tmp/ 약 13GB, 결과 data/ 약 1GB.
#    macOS 기본 파일시스템은 대소문자를 구분하지 않아 같은 저장소 안의 파일이 겹칠 수 있다.
hdiutil create -size 60g -type SPARSE -fs "Case-sensitive APFS" -volname CredDataCS CredData-cs.sparseimage
hdiutil attach CredData-cs.sparseimage
git clone https://github.com/Samsung/CredData /Volumes/CredDataCS/CredData
cd /Volumes/CredDataCS/CredData && git checkout 0b1940e171725ad8937311120b191602608a4801
python3 -m venv .venv && .venv/bin/pip install pybase62==1.0.0
.venv/bin/python download_data.py --jobs 8        # 받은 뒤 T 값을 난독화한다

# 2. tmp/와 .venv/를 빼고 일반 폴더로 옮긴 뒤 볼륨 삭제
rsync -a --exclude tmp --exclude .venv /Volumes/CredDataCS/CredData/ ../CredData/
hdiutil detach /Volumes/CredDataCS && rm CredData-cs.sparseimage

# 3. 변환과 검증 (이 저장소 루트에서)
python metric-detection/scripts/convert_creddata.py --creddata ../CredData
python metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_CredData.jsonl --creddata ../CredData
```

## 정답

[LABELING.md](LABELING.md)의 기준으로 다시 판정한다(`convert_creddata.py`의 `judge()`, `label_rules.py`). CredData의 행은 후보로만 쓰고 T/F/X 판정은 남기지 않는다. CredData는 "저장소에 있는 이 문자열이 실제로 살아 있는 자격증명인가"를 판정한 데이터라, 테스트 값과 약한 비밀번호를 X나 F로 둔다. 우리는 "에이전트 트래픽에서 가려야 하나"를 보므로 자격증명 자리에 있으면 이런 값도 정답이다.

CredData의 행 범위는 값이 아닐 때가 있다(문장 전체, `key: value`, `user:pw`). 판정 전에 값만 남긴다(`locate_value()`). 범위가 없는 줄에 있는 값도 읽는다. 창 안의 줄에서 자격증명 자리에 든 리터럴(`label_rules.slot_literals`)은 CredData 행이 없어도 정답이다.

| 판정 | 행 | 기준 |
|---|---|---|
| 정답: 개인키 | 1,481 | 본문이 있는 개인키 블록, 또는 PEM 포장이 없는 키 재료(base64 PEM, PASERK, NKEY seed, 개인 성분이 있는 JWK) |
| 정답: 자격증명 자리 | 10,289 | `label_rules.classify`의 자격증명 자리(`"password": "test"`, `aws_secret_access_key='dummy'`, `postgres://user:⟦pw⟧@host`). 키 뒤의 따옴표 없는 값은 리터럴로 읽힐 때만(`label_rules.is_literal`) 정답이다 |
| 정답: 키 재료 | 4,005 | 키 이름 뒤의 hex·base64 값(`Key = 9f2c…`, `SharedSecret=…`), 헤더 이름 없는 `"Bearer …"` |
| 정답: 형식 | 344 | 서비스 접두어 토큰, JWT처럼 형식만으로 자격증명인 값 |
| 정답: 행 없는 자리 | 227 | CredData 행이 없는 줄의 리터럴 |
| 음성: 제외 규칙 | 33,658 | `label_rules.exclusion_kind`: 설명 문구·화면 문구(`descriptor`), 코드(`code`), 자리표시자(`template`), 가린 흔적(`redaction`), 식별자, 문서 예시, 변수 참조, 해시 |
| 음성: 자격증명 자리 아님 | 18,092 | 위 어디에도 들지 않는 값(`nonce`, `salt`, `x-github-request-id`, `appid`) |

정답 값이 세션의 다른 곳에 또 나오면 퍼뜨림 기준(`label_rules.judge_occurrence`)을 따른다. 그렇게 정답이 된 등장이 886곳, 정답이 아닌 등장이 4,252곳이다(labels의 `creddata_id`가 비어 있는 행).

2026-11-06에 CredData의 T 판정으로 정답을 정하던 예외를 없앴다. 이 예외로 정답이 된 값이 6,000개를 넘었고, `nonce`, `salt`, 요청 id처럼 자격증명이 아닌 값이 섞여 있었다. 판정이 텍스트 규칙만 따르면서 T였던 값도 자리나 형식을 규칙이 읽지 못하면 음성이 된다. `ROTP::TOTP.new('…')`처럼 사람은 알아보지만 규칙에 없는 자리가 그런 경우다.

## 결과 (`--context-lines 10`)

| 파일 | 내용 |
|---|---|
| `sessions_from_CredData.jsonl` | 라벨된 파일 하나가 세션 하나. item은 라벨된 줄 ±10줄 창이고, 겹치는 창은 합친다. channel은 `tool_output` (에이전트가 파일을 읽어 받은 도구 결과로 본다) |
| `gold_from_CredData.jsonl` | 정답 span. `gold.jsonl`과 같은 형식 |
| `labels_from_CredData.jsonl` | CredData 전체 행을 item 좌표로 옮기고 우리 판정(`gold`, `kind`, `rule`)을 붙인 분석용 파일. Category와 Id를 함께 남긴다 |

세션 11,030개, item 25,345개, gold span 17,500개(SECRET 6,761 / PASSWORD 6,060 / TOKEN 3,028 / PRIVATE_KEY 1,459 / ACCESS_KEY 192). 정답인 행과 그 값의 다른 등장(아래)에서 겹치는 것을 정리한 수다(변환 규칙 참고).
gold가 있는 item은 6,432개다. 나머지 item은 스캐너가 후보로 잡았지만 비밀이 아닌 값만 있어서 어려운 음성 데이터로 쓸 수 있다.

## 변환 규칙

- 줄 나누기는 CredData와 같다: `\r\n`과 `\r`을 `\n`으로 바꾼 뒤 `\n`으로 나눈다. offset은 item text의 Python 코드 포인트 기준이다.
- 값 위치: LineStart 줄의 ValueStart부터 LineEnd 줄의 ValueEnd까지. ValueEnd가 없으면 줄 끝까지, ValueStart가 없으면(PEM 전체 줄 라벨) 줄 전체. 앞뒤 공백은 잘라낸다. CredData의 값 범위가 값 뒤까지 넘어간 경우, 줄 이음 `\\`, 뒤따르는 주석(` # …`), 다음 쿼리 인자(`&k=v`)도 잘라낸다(`tidy()`).
- 겹치는 정답: 구성 요소와 겹치는 `… Multi` 조합 규칙 행 96개는 버렸다. 나머지 겹침 115건은 합집합으로 합쳤고, type은 가장 긴 행을 따른다.
- Category → type: 개인키 계열(PEM/BASE64 Private Key, JWK, PASERK, NKEY Seed 또는 CryptographyKey=Private)은 PRIVATE_KEY, `URL Credentials`는 PASSWORD(URL 속 비밀번호 부분), 이름에 Password가 있으면 PASSWORD, AWS Client ID 같은 식별자형은 ACCESS_KEY, Token/Authorization/Auth는 TOKEN, 나머지(Key, Secret, UUID, Salt, Nonce …)는 SECRET이다. 구현은 `convert_creddata.py`의 `gold_type()`에 있다.

## 점수를 읽을 때 유의할 점

- **음성은 일부러 어렵게 고른 표본이다.** 스캐너가 후보로 잡았지만 비밀이 아닌 값이 많다. 그래서 이 데이터의 precision과 1,000줄당 과잉 마스킹은 실제 에이전트 트래픽의 오탐률이 아니다. 합성 데이터의 precision과 나란히 비교하지 않는다.
- **CredSweeper와 비교할 때 편향이 있을 수 있다.** CredData의 후보는 스캐너 결과에서 나왔고, CredData와 CredSweeper는 둘 다 Samsung이 만들었다.
- **라벨 없는 주변 줄도 음성이다.** item은 라벨된 줄의 ±10줄 창이다. 라벨 없는 줄에 실제 자격증명이 있으면 그것을 가린 것도 과잉 마스킹이 된다.
- **값은 난독화되어 있다.** CredData가 원본 비밀을 같은 모양의 임의 문자열로 바꿨다. 그래서 공백이 든 무작위 비밀번호처럼 보이는 값도 있다.
- 에이전트 세션이 아니라 저장소 파일 조각이다. 프롬프트나 명령 출력 맥락이 없으므로 채널별 성능은 이 데이터로 판단하지 않는다.
- 과잉 마스킹이 어디서 나왔는지는 `per_edit.jsonl`의 좌표를 `labels_from_CredData.jsonl`의 `kind`와 맞춰 나눠 볼 수 있다.

## 나중에 ML 학습에 쓰게 되면

지금은 평가 전용이지만, 학습에 쓰게 되면 **앞뒤 창(±10줄)에 자격증명이 끼어 있는 item은 학습 데이터에서 빼야 할 수 있다.** 창 안의 라벨 없는 줄에 있는 자격증명은 gold가 없으므로 음성으로 학습된다. 라벨된 줄 하나를 주변 줄과 함께 판정하는 모델이라면, 창 안의 다른 T 값도 그 줄의 라벨과 상관없는 신호가 된다. 학습에 쓰려면 [dataset_policy.py](scripts/dataset_policy.py)의 `external` 용도도 함께 바꿔야 한다.
