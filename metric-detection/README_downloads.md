# 변환 대기 중인 외부 소스 (원본만 받아 둔 상태)

2026-10-14에 탐색 보고서의 채택 소스 원본을 받아 두었다. 아직 변환하지 않았고, train/dev/test 분할도 정하지 않았다. 기존 소스와 같이 원본은 저장소 옆 폴더(`../<이름>`)에 두고, 커밋을 고정하고, git에는 올리지 않는다. 디스크를 아끼려고 규칙·테스트 폴더만 sparse checkout으로 받았다.

| 보고서 # | 소스 | 폴더 | 커밋 | 라이선스 | 받은 범위 | 크기 |
|---|---|---|---|---|---|---|
| 1 | Kingfisher 자체 규칙 (v1) | `../kingfisher-v1` | `4666a2dd990edb34f7c5b6f9a9985c9a8b8c6752` (2026-08-12) | Apache-2.0 | `crates/kingfisher-rules/data/rules/` 623개 파일, 규칙 약 1,090개, 전부 `examples` 있음 | 2.8MB |
| 1 | Kingfisher 현재 (v2) | `../kingfisher` | `8244f7bdbc8d9fa08514205a6394da7318e06812` (2026-10-12) | Apache-2.0 | `crates/kingfisher-rules/` (가져온 규칙 488개와 출처 목록) | 15MB |
| 2 | Titus | `../titus` | `efdea19b8420c36a50a5f08194f9c3b02e250025` | Apache-2.0 | `pkg/rule/`, `testdata/` | 2.3MB |
| 3 | secretlint | `../secretlint` | `ca54b6b34e6ec440a48f3e29d3f4dc31283b22c5` | MIT | `packages/@secretlint/secretlint-rule-*/` | 5.8MB |
| 4 | TruffleHog | `../trufflehog` | `6404b6330c2f75f3d62757f3e642bebdde6bbc7b` | AGPL-3.0 | `pkg/detectors/` (`_test.go` 1,861개) | 15MB |
| 5 | whispers (Skyscanner) | `../whispers` | `5832bf74dcb127128ba653ed87601c927124b5aa` | Apache-2.0, 보관됨 | 전체 | 0.9MB |
| 5 | whispers v2 (adeptex) | `../whispers-adeptex` | `24ee0f03490c0a6607e4d6fd960a791d1a7ff50f` | BSD-3-Clause | 전체 | 1.1MB |
| 6 | CodeIPI | `../inspect_evals` | `4e0615e5fd5eadd55a3508a8c20d1b97de992f5b` | MIT | `src/inspect_evals/ipi_coding_agent/` (샘플은 `dataset/samples.json`), `agent_artefacts/ipi_coding_agent*/` | 1.7MB |
| 9 | SafeClawArena | `../SafeClawArena` | `c4e8c395a7716f9da123db6b8038cb8021846361` | MIT | 전체 (`tasks/` cdf 146·ssi 100·ipi 100·pse 60) | 22MB |
| 13 | OWASP WrongSecrets | `../wrongsecrets` | `ae5df50698ed5feb972471e21a2306a2760a5a6d` | AGPL-3.0 | 전체 중 이미지 제외 | 264MB |
| 17 | Semgrep rules | `../semgrep-rules` | `9bbf021d0acffa3095fcffd17b2bc7787eb4796d` | Semgrep Rules License v1.0 | `generic/secrets/` (`gitleaks/` 343개, `security/` 100개 파일) | 2.8MB |
| 7 | MSR 2026 이슈 데이터셋 | `../msr-issue-secrets` | Zenodo 19622962 (2026-04-16, 최신) | CC BY 4.0 | zip 전체(MD5 `af40bd3329508fb47ed1b37143fd43df`). 양성 값을 치환한 `sanitized/`만 쓴다(아래 "MSR 양성 값 치환") | 134.5MB (zip) |

## 받으면서 확인한 것

- **Kingfisher**: 2026-08-21 커밋 `cecc7229`("Import Kingfisher v2 snapshot")에서 자체 규칙을 지우고 Betterleaks 규칙 461개와 Google Veles 규칙 27개를 가져다 쓰는 구조로 바뀌었다. 현재 커밋의 규칙은 모두 gitleaks 계열이라 순환 위험이 높다. 그래서 headline에는 v1 자체 규칙을 쓰고, 현재 커밋은 Betterleaks 차이분(보고서 #16)을 확인하는 용도로만 둔다. v1 규칙 중에도 gitleaks에서 온 것이 있는지는 아직 보지 않았다.
- **SafeClawArena**: 코드와 과제가 공개돼 있고 MIT라 선행 확인을 통과했다.
- **WrongSecrets**: AGPL-3.0. `src/main/resources/executables/`에 챌린지 실행 파일(Go·Swift 바이너리)이 들어 있다. 실행하지 말고 정적으로만 다룬다.
- **Semgrep**: `generic/secrets/` 안에서 `ruleid:` 주석이 달린 테스트 파일 216개를 찾았다(규칙별 테스트가 있다). 라이선스상 내부 평가에만 쓴다(아래 라이선스 판단).
- **whispers v2**: 라이선스가 BSD-3-Clause로 Skyscanner판(Apache-2.0)과 다르다.
- **MSR 이슈 데이터셋**: README 기준 음성은 48,267건이다(5,881 + 48,267 = 54,148). 탐색 보고서의 48,297은 오기다. zip 구조는 `Data/main_data.csv`, `train.csv`, `val.csv`, `test.csv`, `test_wild.csv`(178개 저장소)와 노트북·코드다. 양성은 검증하지 않은 실제 유출값이라 받은 뒤 바로 치환했다.

## 라이선스 판단 (2026-10-14)

받는 것은 모두 허용된다. 차이는 변환 결과를 어디까지 쓰고 공개하느냐에 있다. 이 저장소는 공개 저장소이므로, 변환 결과는 기존 소스처럼 `.gitignore`에 넣고 다시 만드는 방식으로 둔다.

| 라이선스 | 소스 | 평가 | 학습 | 변환 결과 공개 | 조건 |
|---|---|---|---|---|---|
| MIT · Apache-2.0 · BSD-3 | Kingfisher, Titus, secretlint, whispers 2종, CodeIPI, SafeClawArena | 가능 | 가능 | 가능 | 저작권·라이선스 고지 유지. Apache는 NOTICE 포함 |
| AGPL-3.0 | TruffleHog, WrongSecrets | 가능 | 가능(내부) | 하지 않음 | 의무는 배포하거나 수정한 프로그램을 네트워크 서비스로 제공할 때 생긴다. 변환 데이터를 공개하면 AGPL 파생물로 볼 여지가 있어 내부에만 둔다 |
| Semgrep Rules License v1.0 | Semgrep | 내부에서만 | 하지 않음 | 금지 | "your own internal business purposes"로만 사용, 배포와 서비스 제공 금지, 고지 유지, 수정본에는 수정 표시. 학습이나 연구에 관한 조항은 없다. 학생 과제가 "internal business"인지 분명하지 않아 평가에만 쓴다 |
| CC BY 4.0 | MSR 이슈 데이터셋 | 가능 | 가능 | 원문은 하지 않음 | 출처 표기(논문·라이선스 링크·변경 사실). 아래 주의 참고 |

**MSR 데이터셋 주의**
- Zenodo에서 공개(open access)이고 CC BY 4.0이라, 받기·가공·학습 모두 저작권상 허용된다.
- CC BY 4.0은 저자가 가진 권리만 허락한다. 2(b)(1)항에 따라 프라이버시권은 허락 대상이 아니다. 이슈 본문은 GitHub 사용자의 글이고, 비밀값은 제3자의 자격증명이다.
- GitHub 이용 정책 7절은 연구 목적으로 "public, non-personal information"을 쓰도록 허용하고, 결과 출판물은 open access여야 한다고 정한다. 이 조건은 다른 경로로 얻은 정보에도 적용된다. 따라서 사용자명·이메일 같은 개인정보는 가리고, 결과를 공개할 때는 open access로 한다.
- 비밀값을 실제로 호출해 유효성을 확인하는 것은 라이선스와 별개로 무단 접근이므로 하지 않는다. 받은 뒤 양성 값은 형식을 보존해 치환하고 원본은 지운다(탐색 보고서의 계획).

**Kingfisher v1 출처**: NOTICE에 Veles(Apache-2.0), Nosey Parker·Titus(Apache-2.0), Betterleaks·Gitleaks(MIT)에서 가져온 규칙 파일 목록이 있다. 라이선스는 모두 허용형이다. Gitleaks·Betterleaks 유래 파일은 순환 관리상 gitleaks 하위 집합으로 분리할 때 이 목록을 쓴다.

## MSR 양성 값 치환 (2026-10-14)

[scripts/sanitize_msr_issues.py](scripts/sanitize_msr_issues.py)가 양성 값을 모두 같은 형식의 가짜로 바꾼 사본을 `../msr-issue-secrets/sanitized/`에 쓴다. 가짜를 만드는 규칙은 [scripts/fmtkeep.py](scripts/fmtkeep.py)에 있다. 원본과 가짜의 대응표는 어디에도 쓰지 않고, 출력과 보고서(`SANITIZE_REPORT.json`)에는 개수와 모양만 남긴다.

**지키는 것**: 라벨, id, 행 순서, 텍스트가 아닌 열이 원본과 같다. 텍스트 필드도 길이가 같아 원본에서 계산한 위치(offset)를 그대로 쓸 수 있다. 예외는 URL 인코딩된 base64가 들어 있어 `%2B`·`%2F`의 위치가 바뀐 3개 필드다. 가짜는 고정 접두사(Kingfisher v1 규칙, 데이터에서 배운 접두사, 업체 접두사 목록), 자리별 글자 종류와 문자 집합, 체크섬, base64 정규형, JWT의 JSON 키와 헤더, DER/PEM 구조, SSH 키 형식, 그리고 원본이 맞는 Kingfisher 규칙 집합을 유지한다.

**값이 아니라 토큰 단위로 바꾼다**: 양성 값 5,850개(약한 값 제외) 중 2,118개는 본문에서 더 긴 토큰의 일부였다. Artifactory 후보는 JWT나 base64에서 잘라 낸 73자, Alibaba 후보는 30자 조각, Contentful 후보는 앞 두 글자가 빠진 값이다. 후보만 바꾸면 토큰의 나머지가 실제 값으로 남으므로, 값이 나오는 자리마다 감싸는 토큰(같은 문자 구간, JWT, base64 블롭, 여러 줄 블롭, PEM 블록)으로 넓혀 그 토큰을 치환하고, 값의 가짜는 토큰 가짜에서 같은 위치를 잘라 쓴다. 잘린 context_window나 이스케이프된 표기에 남은 조각은 12자 조각(무작위 문자열처럼 보이고 가짜에서 6자 이상 바뀌는 것)으로 원래 토큰에 맞춰 바꾼다.

**일부러 두는 것**: JWT/JOSE 헤더(`{"alg":..,"typ":..}`, 공개 메타데이터)와 헤더 뒤 `.eyJ`, 키 이름과 공개 구조. 8자 미만이거나 단어 같은 약한 값은 후보 문자열 전체가 나오는 자리에서만 바꾼다(흔한 단어를 데이터 전체에서 바꾸지 않도록).

**남은 원본**: 마지막 검증에서 `Data/main_data.csv` 51237번째 데이터 행의 `context_window` 한 칸에 원본 12자 조각 2개가 원래 자리에 남았다(`SANITIZE_REPORT.json`의 `leftover_places`). 원인을 더 찾지 않고 `--allow-leftovers`로 그대로 썼다. 이 행을 공개하거나 예시로 인용하지 않는다.

**한계**: 값 131개는 서로 다른 두 토큰 이상에 들어 있어 토큰마다 가짜가 따로 만들어졌다. 그래서 같은 행에서 후보 문자열의 가짜와 본문의 해당 위치가 다른 경우가 645곳 있다(일치 21,355곳). 판정 위치를 본문에서 다시 찾는 평가라면 이 행들을 확인해야 한다.

**독립 검사 결과(미해결)**: 치환기와 별개로, 양성 값이 나오는 자리마다 그 주변 문자 구간에서 무작위처럼 보이는 16자 창이 원래 자리에 그대로 남았는지 셌다. 33,597곳 중 3,804곳에서 남은 창이 나왔다. 표본으로 본 것은 모두 일부러 두는 공개 구조였다. SSH 공개키 머리(`AAAAB3NzaC1yc2EAAAADAQAB…`), PKCS#8 개인키의 DER 머리, JWT 헤더와 페이로드의 JSON 키(base64), 환경변수 이름 같은 것들이다. 다만 전부 확인하지는 않았다. 서로 다른 남은 창 43,162개 중 6,060개는 양성 값 하나에만 나온다. 공유 구조라고 단정할 수 없으니, 데이터를 밖으로 내보내기 전에는 이 검사를 더 정밀하게(디코딩한 구조 기준으로) 다시 해야 한다.

**다시 만들기**: 아래 "다시 받기"의 MSR 줄로 zip을 받아 압축을 풀고 실행한다. 가짜는 매번 무작위라 실행마다 다르다. 약 12분 걸린다.

```bash
cd metric-detection/scripts
python3 sanitize_msr_issues.py --src ../../../msr-issue-secrets/raw/extracted/Secret-Leak-Detection-Issue-Report \
    --out ../../../msr-issue-secrets/sanitized --kingfisher ../../../kingfisher-v1 --allow-leftovers
```

`--allow-leftovers`를 빼면 검증에서 원본이 하나라도 남을 때 아무것도 쓰지 않고 멈춘다.

## 다시 받기

```bash
cd ..   # promptguard-data 옆
clone() {  # clone <github 저장소> <폴더> <커밋> <sparse 경로...>
  git clone --filter=blob:none --no-checkout "https://github.com/$1" "$2"
  local repo=$1 dir=$2 rev=$3; shift 3
  [ $# -gt 0 ] && git -C "$dir" sparse-checkout set --no-cone "$@"
  git -C "$dir" checkout -q "$rev"
}
clone mongodb/kingfisher kingfisher-v1 4666a2dd990edb34f7c5b6f9a9985c9a8b8c6752 '/crates/kingfisher-rules/data/rules/' '/docs/RULES.md' '/LICENSE' '/NOTICE'
clone mongodb/kingfisher kingfisher 8244f7bdbc8d9fa08514205a6394da7318e06812 '/crates/kingfisher-rules/' '/docs/RULES.md' '/LICENSE' '/NOTICE'
clone praetorian-inc/titus titus efdea19b8420c36a50a5f08194f9c3b02e250025 '/pkg/rule/' '/testdata/' '/LICENSE' '/NOTICE'
clone secretlint/secretlint secretlint ca54b6b34e6ec440a48f3e29d3f4dc31283b22c5 '/packages/@secretlint/secretlint-rule-*/' '/LICENSE'
clone trufflesecurity/trufflehog trufflehog 6404b6330c2f75f3d62757f3e642bebdde6bbc7b '/pkg/detectors/' '/LICENSE'
clone Skyscanner/whispers whispers 5832bf74dcb127128ba653ed87601c927124b5aa
clone adeptex/whispers whispers-adeptex 24ee0f03490c0a6607e4d6fd960a791d1a7ff50f
clone UKGovernmentBEIS/inspect_evals inspect_evals 4e0615e5fd5eadd55a3508a8c20d1b97de992f5b '/src/inspect_evals/ipi_coding_agent/' '/agent_artefacts/ipi_coding_agent*/' '/LICENSE'
clone sunblaze-ucb/SafeClawArena SafeClawArena c4e8c395a7716f9da123db6b8038cb8021846361
clone OWASP/wrongsecrets wrongsecrets ae5df50698ed5feb972471e21a2306a2760a5a6d '/*' '!*.png' '!*.jpg' '!*.jpeg' '!*.gif' '!*.mp4' '!*.webp' '!*.ico' '!*.svg' '!*.pdf'
clone semgrep/semgrep-rules semgrep-rules 9bbf021d0acffa3095fcffd17b2bc7787eb4796d '/generic/secrets/' '/LICENSE' '/README.md'
mkdir -p msr-issue-secrets/raw && curl -sSL -o msr-issue-secrets/README.md https://zenodo.org/api/records/19622962/files/README.md/content
curl -sSL -C - -o msr-issue-secrets/raw/Secret-Leak-Detection-Issue-Report.zip https://zenodo.org/api/records/19622962/files/Secret-Leak-Detection-Issue-Report.zip/content
md5 -q msr-issue-secrets/raw/Secret-Leak-Detection-Issue-Report.zip   # af40bd3329508fb47ed1b37143fd43df
unzip -q msr-issue-secrets/raw/Secret-Leak-Detection-Issue-Report.zip -d msr-issue-secrets/raw/extracted
```
