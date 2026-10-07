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

# 3. 변환과 검증 (이 저장소 루트에서). metric-1/creddata_review.jsonl의 판정이 gold에 반영된다
python metric-1/scripts/convert_creddata.py --creddata ../CredData
python metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_CredData.jsonl --creddata ../CredData
```

## X/F 검수

지표 1의 정답은 "실제로 인증에 쓰이는 자격증명인가"다([metric-1/README.md](README.md#정답의-정의)). CredData의 X(템플릿·placeholder)와 F는 대부분 이 기준에서도 자격증명이 아니다. 다른 것은 **동작하는 테스트 값과 설정된 기본·약한 비밀번호**다. CredData는 이런 값을 X나 F로 두지만, 우리 기준에서는 자격증명이다. 예를 들어 `x-pack-test-password`는 X로 63번, F로 51번 라벨되어 있다. 그래서 X/F는 기본적으로 CredData 판정대로 음성으로 쓰고, 이런 예외만 값 단위로 골라 `CRED`로 고친다. 전부 검수하지 않는다.

### 현재 판정 (2026-10-07)

설정된 약한 비밀번호일 수 있는 값과 동작하는 테스트 값 11개를 보수적으로 `CRED`로 정했다. 놓치면 실제 비밀이 노출될 수 있기 때문이다. 그 값의 X/F 행 전부에 그룹 판정으로 적용했다.

| 값 | 행 수 (X / F) |
|---|---|
| `secret` | 445 (437 / 8) |
| `password` | 361 (323 / 38) |
| `pass` | 230 (170 / 60) |
| `test` | 148 (143 / 5) |
| `pwd` | 105 (97 / 8) |
| `x-pack-test-password` | 114 (63 / 51) |
| `Test Secret` | 35 (35 / 0) |
| `SECRET1` | 27 (27 / 0) |
| `s3krit-password` | 26 (0 / 26) |
| `12345` | 24 (21 / 3) |
| `PASS` | 22 (3 / 19) |
| 합계 | 1,537 (1,319 / 218) |

행이 가장 많은 나머지 값은 그대로 음성이다. `1234abcd-12ab-34cd-56ef-1234567890ab`(2,260행)와 `12345678-1234-1234-1234-123456789012`(1,088행)는 AWS SDK API 문서의 KMS 키 ID·ARN 예시다. 문서 예시 값이고, 실제 값이라도 리소스 식별자일 뿐 자격증명이 아니다. `login_and_password_removed`(536행)는 원래 값을 지운 흔적이다.

### 검수 페이지

```bash
python metric-1/manual_review/review_creddata.py --creddata ../CredData   # http://127.0.0.1:8765 를 연다
```

- 대상: 값 위치가 있는 한 줄짜리 X/F 행(X 4,079 · F 15,480). 줄 전체를 표시한 F 행은 제외한다.
- 판정은 `CRED`(자격증명) 또는 `NOT_CRED`(아님) 둘 중 하나다. 과제에 필요한지(MASK/KEEP)는 여기서 보지 않는다. 그건 지표 3의 라벨이다.
- 같은 문자열은 X와 F를 합쳐 한 그룹으로 묶는다(6,894개). 그룹 판정은 그 값의 모든 행에 적용되고, 행마다 따로 판정할 수도 있다. CredData 위치가 틀린 행(예: `password: admin`에서 `dmin`)은 줄에서 드래그해 범위를 고친다. 범위를 고친 행은 `CRED`가 된다.
- 바꿀 때마다 `metric-1/creddata_review.jsonl`에 저장된다. CredData id와 판정만 들어 있고 파일 본문이 없으므로 커밋한다. 행의 `Id`가 이 파일에 있으면 검수한 행이다.
- **완료 · gold 생성**을 누르면 `convert_creddata.py`를 다시 실행해 `*_from_CredData.jsonl`을 새로 쓴다. `CRED` 행은 gold가 된다. `NOT_CRED` 행과 검수하지 않은 행은 CredData 판정대로 음성으로 남는다.
- 서버는 127.0.0.1에서만 연다. 화면에 CredData 파일 본문이 나오기 때문이다.

## 결과 (`--context-lines 10`)

| 파일 | 내용 |
|---|---|
| `sessions_from_CredData.jsonl` | 라벨된 파일 하나가 세션 하나. item은 라벨된 줄 ±10줄 창이고, 겹치는 창은 합친다. channel은 `tool_output` (에이전트가 파일을 읽어 받은 도구 결과로 본다) |
| `gold_from_CredData.jsonl` | CredData T 행과 검수에서 `CRED`로 판정한 X/F 행. `gold.jsonl`과 같은 형식 |
| `labels_from_CredData.jsonl` | CredData 전체 행(T/F/X)을 item 좌표로 옮긴 분석용 파일. 원래 Category와 Id, 검수 대상 여부(`reviewable`)와 판정(`review`)을 함께 남긴다 |

현재 판정 반영: 세션 11,030개, item 25,345개, gold span 17,133개(SECRET 8,729 / PASSWORD 4,022 / TOKEN 2,623 / PRIVATE_KEY 1,424 / ACCESS_KEY 335). CredData T가 15,596개, `CRED`로 판정한 X/F가 1,537개다.
item 중 gold가 없는 19,103개는 대부분 CredData F 행(스캐너가 잡았지만 사람이 비밀이 아니라고 본 줄)을 포함한다. 그래서 어려운 음성 데이터로 쓸 수 있다.

## 변환 규칙

- 줄 나누기는 CredData와 같다: `\r\n`과 `\r`을 `\n`으로 바꾼 뒤 `\n`으로 나눈다. offset은 item text의 Python 코드 포인트 기준이다.
- 값 위치: LineStart 줄의 ValueStart부터 LineEnd 줄의 ValueEnd까지. ValueEnd가 없으면 줄 끝까지, ValueStart가 없으면(PEM 전체 줄 라벨) 줄 전체. 앞뒤 공백은 잘라낸다.
- 검수 `CRED` 행: CredData 위치(또는 검수에서 고친 위치)를 T와 같은 방식으로 gold에 넣는다. type은 Category에서 정한다.
- 겹치는 T: 구성 요소와 겹치는 `… Multi` 조합 규칙 행 45개는 버렸다. 나머지 겹침 112건은 합집합으로 합쳤고, type은 가장 긴 행을 따른다.
- Category → type: 개인키 계열(PEM/BASE64 Private Key, JWK, PASERK, NKEY Seed 또는 CryptographyKey=Private)은 PRIVATE_KEY, `URL Credentials`는 SECRET, 이름에 Password가 있으면 PASSWORD, AWS Client ID 같은 식별자형은 ACCESS_KEY, Token/Authorization/Auth는 TOKEN, 나머지(Key, Secret, UUID, Salt, Nonce …)는 SECRET이다. 구현은 `convert_creddata.py`의 `gold_type()`에 있다.

## X/F를 음성으로 쓸 때 유의할 점

점수를 해석할 때 주의한다. 판정하지 않은 X/F는 CredData 판정을 그대로 따른다.

- **precision은 하한값이다.** 판정하지 않은 X/F에도 우리 기준으로는 자격증명인 값(동작하는 테스트 값, 설정된 약한 비밀번호)이 남아 있을 수 있다. 탐지기가 이런 값을 가리면 과잉 마스킹으로 센다. gold에는 없으므로 recall은 영향을 받지 않는다.
- **음성은 일부러 어렵게 고른 표본이다.** F는 스캐너가 후보로 잡았지만 사람이 비밀이 아니라고 본 줄이다. 그래서 이 데이터의 precision과 1,000줄당 과잉 마스킹은 실제 에이전트 트래픽의 오탐률이 아니다. 합성 데이터의 precision과 나란히 비교하지 않는다.
- **CredSweeper와 비교할 때 편향이 있을 수 있다.** CredData의 라벨 후보는 스캐너 결과에서 나왔고, CredData와 CredSweeper는 둘 다 Samsung이 만들었다. 그래서 이 데이터에서는 CredSweeper가 유리할 수 있다.
- **라벨 없는 주변 줄도 음성이다.** item은 라벨된 줄의 ±10줄 창이다. 라벨 없는 줄에 실제 자격증명이 있으면 그것을 가린 것도 과잉 마스킹이 된다.
- 과잉 마스킹이 X, F, 라벨 없는 줄 중 어디서 나왔는지는 `per_edit.jsonl`의 좌표를 `labels_from_CredData.jsonl`과 맞춰 나눠 볼 수 있다.

## 우리 라벨 기준과 다른 점

- 동작하는 테스트 값과 설정된 기본·약한 비밀번호: CredData는 X나 F로 두지만 우리 기준에서는 자격증명이다. `CRED`로 판정한 행만 gold에 들어간다(**현재 판정**).
- placeholder·지운 흔적(`login_and_password_removed`, `<password>` 등), 변수 참조, 문서의 예시 값: CredData와 우리 기준 모두 자격증명이 아니다. 규칙 기반 탐지기가 자격증명 자리라서 가리면 과잉 마스킹으로 센다.
- T 값은 난독화되어 있어 X/F 값과 문자열로 대조할 수 없다. 같은 값의 T/X 판정 차이는 검수 화면에서 보이지 않는다.
- CredData는 맥락상 자격증명이면 UUID도 T로 본다(예: 일부 `x-github-request-id`). 우리 합성 데이터에서는 request id를 정답에 넣지 않는다.
- T 값은 CredData가 원본 비밀을 같은 모양의 임의 문자열로 바꾼 난독화 값이다. 실제 비밀은 들어 있지 않다.
- 에이전트 세션이 아니라 저장소 파일 조각이다. 프롬프트나 명령 출력 맥락이 없으므로 채널별 성능은 이 데이터로 판단하지 않는다. 과제도 없으므로 지표 3 라벨은 붙이지 않는다.
