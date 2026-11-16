# CredData 기반 작업·궤적 수집 파일럿

작업군은 코드 분석, 문서 작성, 리팩터링(설정 파일 변환 포함), 테스트 코드 작성이다.
모든 작업은 같은 원본·작업군에 대해 한국어 지시문과 영어 지시문 한 쌍으로 발급한다.
지시문은 [instructions_v2.json](instructions_v2.json)의 공통 템플릿 8개(작업군 4 × 지시문 언어 2)이며
`{source_file}`, `{source_language}`만 치환한다. 원본별 지시문을 LLM으로 쓰지 않는다.
구체적인 분석·수정·테스트 대상은 작업 에이전트가 고른다.

| 카탈로그 (`runs/` 아래) | 기본 작업 | 환경(한·영) | 원본 | 만드는 법 |
|---|---|---|---|---|
| `creddata-pilot-v2-bilingual` | 20 | 40 | Python/JSON 9파일·9저장소 | [pilot_v1.json](pilot_v1.json)을 한영 쌍으로 재발급 |
| `creddata-auto-v1-bilingual` | 100 | 200 | Python/JSON 70파일·31저장소 | `creddata-auto-v1`을 한영 쌍으로 재발급 |
| `creddata-auto-v2-bilingual-r2` | 100 | 200 | 17개 언어·형식 99파일·70저장소 | 다중 언어 자동 확장 (기본값) |
| `creddata-auto-v3-fullfile` | 100 | 200 | 원본 파일 전체 100개·74저장소 (파싱하는 15개 언어·형식 + 파싱하지 않는 19개 형식) | 파일 전체·CredData Category 값 ([아래](#원본-파일-전체와-category-값-v3)) |

작업군·지시문 언어별 개수는 카탈로그마다 같다(5·25·25). 세 카탈로그는 원본과 과제를 서로 재사용하고,
한 카탈로그 안에서도 같은 원본으로 여러 작업을 만든다. 환경 440개를 독립적인 과제 440개로 세면 안 된다.
`task_pair_id`가 같은 두 환경은 원본·split·component가 같고, 같은 seed로 만들면 코드와 주입값도 같다.
`instruction_language`는 지시문 언어(ko/en), `language`·`source_language`는 코드 언어다.

`creddata-pilot-v1`(한국어 전용 지시문, Haiku 4회 실행 기록 포함)과 `creddata-auto-v1`(한국어 전용 100개)은
이전 버전으로 그대로 보존한다. `creddata-auto-v2-bilingual`은 r2와 원본·코드·주입값이 같고 메타데이터 문구
(`selection_note`, `eligibility.method`, README)만 옛 표현인 이전 발급본이다.

## 작업 성공 점수는 만들지 않는다

이 파일럿은 벤치마크가 아니다. 정답 풀이, 성공 채점기, 합격 점수는 없다.
실행 종료 상태, 사용한 토큰·비용, 도구 호출·결과, 알려진 비밀값의 등장과 span을 기록한다.
`run.json`의 `finished`는 CLI가 정상 종료됐다는 뜻이며 과제를 올바르게 풀었다는 뜻은 아니다.

로컬 검사는 데이터 제작 오류를 찾기 위한 것이다. 원본이 train에 속하는지, 값을 넣은 파일이 파싱되는지,
위치가 맞는지, 작업군·지시문 언어별 개수와 한영 쌍의 일치만 검사한다.

## 템플릿과 값 주입

저장소 루트에서 실행한다.

```bash
python3 metric-detection/scripts/creddata_tasks.py build
python3 metric-detection/scripts/creddata_tasks.py instantiate \
  --task all --seed bilingual-check-01 --out runs/creddata-pilot-v2-bilingual/instances/bilingual-check-01
```

`build`의 기본 설정은 [pilot_v2_bilingual.json](pilot_v2_bilingual.json), 기본 출력은
`runs/creddata-pilot-v2-bilingual/templates`다. 다른 카탈로그는 `--pack <카탈로그>/templates`로 지정한다.

생성 파일과 원본 코드 사본은 라이선스·비밀값 관리를 위해 git에서 제외된 `runs/` 아래에 둔다.
각 원본 파일은 원래 저장소의 라이선스를 유지한다. tracked 설정에는 원본 본문과 비밀값을 넣지 않는다.

```text
runs/creddata-pilot-v2-bilingual/
  tasks.json                  작업 정의 (작업 ID는 <기본 ID>__ko, <기본 ID>__en)
  templates/<task>/
    task.json                 원본 ID, split, component, placeholder와 원본 위치 대응
    workspace/subject.*       비밀값 자리가 {{secret:ID}}인 템플릿
    workspace/request.md      치환이 끝난 작업 지시문
  instances/<seed 이름>/<task>/
    task.json
    workspace/                에이전트가 작업할 파일
    private/registry.json     실제 주입값과 주입 후 원본 span (작업 폴더 밖)
  instances/<seed 이름>/preflight.json   오프라인 검증 기록
```

같은 논리적 값·생성 형식은 같은 placeholder를 공유한다. 기본 생성값은 split·원본 슬롯·seed로 결정한다.
기본 자동 생성값은 원본 비밀값 자리에서 기존 라벨 규칙을 통과하는지 확인하고, 실패하면 고정된 재추첨 시드로
최대 16번 시도한다. 재추첨 횟수는 registry에 남긴다. 이는 기존 규칙과의 일관성 검사이며 규칙 자체의
정확성을 보증하지 않는다. `--values`로 직접 지정한 값은 임의로 변경하지 않는다.
새 seed를 주면 값을 바꿔 넣은 새 작업 환경을 만들 수 있다. 이것은 에이전트 재실행 전 환경 변형이며,
이미 기록한 궤적을 값만 바꾸는 사후 증강은 아직 구현하지 않았다.

원하는 문자열을 직접 넣으려면 한 작업의 `task.json`에서 slot ID를 확인하고, 값 파일을 외부에 작성한다.

```bash
python3 metric-detection/scripts/creddata_tasks.py instantiate \
  --task analysis-01__ko --values /path/to/values.json --out runs/custom-analysis-01
```

values.json은 해당 작업의 slot ID 전체를 키로, 원하는 문자열을 값으로 갖는 JSON 객체다.
따옴표·역슬래시·줄바꿈·유니코드 등은 원본 문자열 종류에 맞게 이스케이프하고 span을 다시 계산한다.
Python은 일반 작은/큰따옴표 문자열, JSON·YAML·TOML은 문자열 스칼라, 그 밖의 언어는 Tree-sitter가
문자열 리터럴로 읽은 자리를 지원한다(`creddata_languages.py`). Python의 raw·bytes·f-string·삼중따옴표,
다른 언어의 interpolation과 일부 raw 리터럴처럼 지원하지 않는 자리는 추측하지 않고 거절한다.
값을 넣은 뒤 구문 검사를 하지만, 임의의 값이 원본 서비스 형식이나 실행 의미까지 보존한다고 보장하지 않는다.

Tree-sitter 파서는 전역 환경을 바꾸지 않고 `runs/tools/creddata-parsers`에만 설치한다.

```bash
python3 -m pip install --target runs/tools/creddata-parsers \
  -r metric-detection/templates/creddata_tasks/parser_requirements.txt
```

## 오프라인 검증

에이전트를 실행하지 않고 발급한 환경 전체를 검사한다. 결과는 `instances/<seed 이름>/preflight.json`에 남는다.

```bash
python3 metric-detection/scripts/creddata_preflight.py \
  --root runs/creddata-auto-v2-bilingual-r2 \
  --instances runs/creddata-auto-v2-bilingual-r2/instances/bilingual-check-01
```

검사 항목은 다음과 같다. 하나라도 실패하면 종료 코드가 1이다.

- 카탈로그: 현재 코드로 `tasks.json`에서 다시 만든 templates가 저장본과 바이트 단위로 같은지, 작업군 ×
  지시문 언어 개수가 같은지.
- 원본: train 소속, component·저장소 상속, 원본 조각 해시, placeholder 자리가 알려진 원본 gold 전부와
  일치하는지, placeholder를 원래 값으로 되돌리면 원본 조각이 복원되는지.
- 환경: 같은 seed로 다시 만든 환경과 바이트 단위로 같은지, placeholder·치환 변수가 남지 않았는지,
  지시문 언어가 맞는지, registry span을 디코드하면 주입값이 나오는지.
- 한영 쌍: 원본 메타데이터, 값을 넣은 원본 파일의 바이트, 주입값·span·seed가 같고 지시문만 다른지.
- 라벨 투영: 값을 넣은 원본 파일을 도구 출력 한 건으로 보고 `creddata_rollout.label_items`에 넣었을 때
  알려진 원본 span이 모두 같은 좌표로 라벨되는지.

2026-11-15 기준 세 카탈로그의 `bilingual-check-01`은 모두 통과했다(원본 span 60·268·280개, 투영 누락 0).
이 검사는 알려진 원본 gold만 다룬다. 등록되지 않은 비밀값까지 주석됐다는 뜻이 아니고, 실제 도구 출력은
줄 번호 등으로 형식이 달라질 수 있으며, 과제의 질이나 에이전트 동작도 검사하지 않는다.

## 소수 실행과 자동 라벨링

인증 방식을 명시해 소수만 먼저 실행한다. `--tasks one-per-family`는 task.json의 작업군과 지시문 언어로
골라, 한영 카탈로그에서는 작업군·지시문 언어별 한 개씩 8개를 고른다. `--instruction-language ko`나 `en`을
주면 그 언어의 4개만 고른다. 한국어 전용 옛 카탈로그에서는 4개다. `--tasks all`이나 쉼표로 나열한 작업 ID도 받는다.
아래 명령의 경로는 예시이며, 한 번 실행한 환경은 다시 실행할 수 없다.
기본은 API 키 방식이며 구독 로그인으로 자동 전환하지 않는다. 키 값은 명령 인자·로그에 기록하지 않는다.

```bash
python3 metric-detection/scripts/creddata_rollout.py run \
  --instances runs/creddata-pilot-v2-bilingual/instances/<seed 이름> \
  --tasks one-per-family --env-file /path/to/anthropic.env --check-only

python3 metric-detection/scripts/creddata_rollout.py run \
  --instances runs/creddata-pilot-v2-bilingual/instances/<seed 이름> \
  --tasks one-per-family --env-file /path/to/anthropic.env --budget 1 --timeout 240
```

ANTHROPIC_API_KEY가 현재 환경에 있으면 `--env-file`을 생략한다. 기본 모델은 CLI의 `sonnet` 별칭이다.
예산은 실행당 Claude CLI의 API 지출 제한이며 실제 비용은 run.json에 기록한다.
중단된 실행을 재실행하려면 기존 환경을 덮어쓰지 않고 새 출력 경로에 instantiate한다.

현재 Claude 구독 계정으로 Haiku만 실행하려면 다음처럼 명시한다. 계정 방식은 로컬 Claude 로그인 정보를
사용하고 API 키·타 제공자 환경변수는 실행 환경에서 제거한다. OAuth를 비활성화하는 `--bare`는 사용하지 않는다.
`--haiku-only`는 프록시에서 비-Haiku 모델 요청을 upstream 전송 전에 차단한다.

```bash
python3 metric-detection/scripts/creddata_rollout.py run \
  --instances runs/creddata-pilot-v2-bilingual/instances/<seed 이름> \
  --tasks one-per-family --auth subscription --model haiku --haiku-only --timeout 240
```

계정 방식의 `cost_usd`는 CLI가 보고한 API 환산 추정치이며 별도 API 청구액이 아니다.
실제 사용된 모델 목록은 `run.json`의 `models_sent`에 기록한다.

기존 api_capture.py를 사용해 인증 헤더를 제외한 API 요청 본문을 기록한다. 기존
convert_trajectory.py의 메시지 추출·문맥 판정만 재사용하며, 기존 평가 파일을 변경하지 않는다.
각 실행의 capture/에 API 요청과 CLI stream을 저장하고, labeled/에 sessions·gold·labels를 출력한다.
prompt, instructions, tool_output뿐 아니라 **에이전트가 쓴 tool_input도 라벨링**한다.
마지막 assistant 응답처럼 후속 API 요청에 들어가지 않은 텍스트는 stream에는 남지만 이 변환의
탐지 입력에는 포함되지 않는다.

## 라벨의 범위

원본의 기존 gold 위치가 placeholder의 출발점이다. 이 라벨은 원래 CredData T/F/X가 아니라
현재 프로젝트 LABELING.md로 변환된 라벨이며 완전한 수동 정답으로 간주하지 않는다.
수집 후 알려진 값과 인코딩 표현을 찾아 문맥별로 판정한다. 미등록 자격증명 후보와 일부만
출력된 값은 review 행으로 분리하고, 라벨이 없는 모든 텍스트가 확실한 음성이라고 주장하지 않는다.

새 기록은 원본 train 분할과 component_id를 상속한다. 기존 external 평가 파일의 용도 정책은
그대로 유지되며 이번 파일럿에 test 원본은 사용하지 않는다. 코드 조각·작업·궤적·증강본을 나중에
다시 임의로 분할하지 않는다. 원본 출처와 기존 평가의 중복을 고려해 전체 CredData 성적을
독립 평가로 보고하면 안 된다.

## 공통 지시문으로 자동 확장

지시문은 [instructions_v2.json](instructions_v2.json)의 작업군·지시문 언어별 템플릿을 그대로 재사용한다.
코드를 보고 지시문을 작성하거나 작업군을 분류하는 LLM 호출은 없다.
원본 하나가 여러 작업군의 후보가 될 수 있으며, 후보에서 작업군별 같은 개수를 선택한 뒤 한영 쌍으로 발급한다.
같은 작업군 안에서는 코드 언어가 한쪽으로 몰리지 않도록 적게 뽑힌 언어를 우선한다.

| 작업군 | 구조적 적용 조건 (`parser_rules_v2_multilanguage`) |
|---|---|
| 코드 분석·문서 작성 | 지원하는 비밀값 문자열 자리와 충분한 비밀값 외 문맥. Python·설정은 구문이 완결돼야 하고, 그 밖의 언어는 파서 오류가 있는 조각(fragment)도 허용 |
| 리팩터링 | Python의 최상위 일반 함수, 다중 필드 설정 객체(JSON/YAML/TOML), 또는 파서 오류가 없고 함수·메서드가 있는 다른 언어 조각 |
| 테스트 코드 작성 | Python의 최상위 일반 함수, 다중 필드 설정 객체, 또는 독립 실행할 수 있는 JavaScript 함수 |

지원 언어·형식은 Python, JSON, YAML, TOML, JavaScript, TypeScript, TSX, Go, Java, Ruby, PHP, C, C++, C#,
Kotlin, Scala, Shell이다. Python은 AST, JSON/YAML/TOML은 해당 파서, 나머지는 Tree-sitter로 확인한다.
현재 후보는 1,123개 조각(790파일, 167저장소)이고 작업군별 후보는 분석·문서 1,123, 리팩터링 149, 테스트 128개다.

Python 일반 함수 후보에서는 main, 기존 test 함수, pass만 있는 함수, 생성기·비동기 함수와 중첩 함수가
있는 조각을 제외한다. 원본 문자열 전체가 아닌 URL 속 일부 값 등은 자동 확장 대상에서 제외한다.
이 규칙은 최소 구조 조건이며 의미상 좋은 개발 과제나 원본 함수의 완전한 의미를 보장하지 않는다.
실행해서 테스트할 수 있도록 지원하는 것은 Python 함수(snippet_loader.py), 독립 JavaScript 함수
(snippet_loader.cjs, Node), 설정의 구조·자료형 검사다. 다른 언어는 빌드·테스트 환경을 제공하지 않으며,
설정 테스트는 원본 애플리케이션 단위 테스트가 아니다. 구문 검사는 원본 앱의 동작 보존을 보증하지 않는다.

```bash
python3 metric-detection/scripts/creddata_tasks_auto.py   # 기본값: --per-family 25 --seed creddata-auto-v2
                                                          #         --max-per-repo 3 --out runs/creddata-auto-v2-bilingual-r2
python3 metric-detection/scripts/creddata_tasks.py instantiate \
  --pack runs/creddata-auto-v2-bilingual-r2/templates --task all --seed bilingual-check-01 \
  --out runs/creddata-auto-v2-bilingual-r2/instances/bilingual-check-01
```

같은 파일과 비밀값을 제거했을 때 동일한 문맥은 한 작업군 안에서 반복하지 않는다.
한 저장소의 과제는 작업군별 최대 3개이며, 작업군 사이에서도 가능한 한 새로운 문맥을 우선한다.
후보가 부족하면 부족한 개수와 사유를 알리고 중복으로 채우지 않는다.
지시문을 바꾸려면 공통 JSON만 수정하고 새 출력 버전으로 생성한다.

생성 결과의 tasks.json은 작업 매핑, eligibility.jsonl은 후보별 적용 가능 작업군과 근거,
selection.json은 제외·선택 통계다. 원본과 코드 사본은 고정 train 분할을 유지하고 runs/ 밖으로 내보내지 않는다.

## 재생성과 이전 버전

생성된 카탈로그는 고정본이다. 같은 명령을 다시 실행하면 저장본과 바이트 단위로 비교해 같으면 통과하고
다르면 덮어쓰지 않고 실패한다. 비교에서 `instances/`만 제외하므로 검증 기록은 `instances/` 아래에 둔다.

```bash
# 옛 작업 정의를 한영 쌍으로 재발급 (원본·작업군 유지, 지시문은 공통 v2 템플릿)
python3 metric-detection/scripts/creddata_tasks_bilingual.py \
  --config metric-detection/templates/creddata_tasks/pilot_v1.json --out runs/creddata-pilot-v2-bilingual
python3 metric-detection/scripts/creddata_tasks_bilingual.py \
  --config runs/creddata-auto-v1/tasks.json --out runs/creddata-auto-v1-bilingual

# 한국어 전용 Python/JSON 자동 확장 (parser_rules_v1, 지시문 4개)
python3 metric-detection/scripts/creddata_tasks_auto.py \
  --instructions metric-detection/templates/creddata_tasks/instructions_v1.json \
  --seed creddata-auto-v1 --out runs/creddata-auto-v1
```

재발급본의 지시문은 옛 지시문을 직역한 것이 아니다. 옛 작업의 지정 대상 함수는 `legacy_target_function`으로만
남기고 새 지시문은 에이전트가 대상을 고르게 한다. 기존 실행 기록은 수정하지 않는다.

## 원본 파일 전체와 Category 값 (v3)

`creddata-auto-v3-fullfile`은 ±10줄 조각 대신 CredData 파일 하나 전체를 원본으로 쓴다. 작업군·지시문 언어별 개수,
저장소 상한(작업군별 3), 결정적 표본 추출, 한영 쌍과 공통 지시문 템플릿(instructions_v2.json)은 v2와 같다.
작업 폴더의 공통 안내문(request.md 첫 부분, README.md)은 "원본 파일 하나 전체"라고 쓴다. 공통 지시문 템플릿에는
여전히 "코드 조각/excerpt"라는 표현이 남아 있다(템플릿을 바꾸지 않기 위해 그대로 둠).

### 재생성 명령 (저장소 루트, CredData clone은 `../CredData`, commit 0b1940e)

```bash
# 1. 파일 전체 변환 (약 10분, runs/ 아래·git 제외). 평가용 data_test/data_answer는 건드리지 않는다.
python3 metric-detection/scripts/convert_creddata.py --creddata ../CredData --context-lines 100000000 \
  --out runs/creddata-source-fullfile
# 2. span별 Category. category_llm/assigned_train.jsonl·uncategorized_train.jsonl은 저장된 입력이며 다시 만들지 않는다.
python3 -B metric-detection/scripts/creddata_gold_categories.py           # --check: 저장본과 바이트 비교
# 3. 자유 형식 Category의 값 프로필
python3 -B metric-detection/scripts/creddata_category_profiles.py build
# 4. 파일 전체 입력의 해시 기록(이미 있으면 비교만 하고 다르면 실패)
python3 -B metric-detection/scripts/creddata_fullfile.py manifest
# 5. 카탈로그, 값 주입, 오프라인 검증
python3 -B metric-detection/scripts/creddata_fullfile.py build --per-family 25 --out runs/creddata-auto-v3-fullfile
python3 -B metric-detection/scripts/creddata_tasks.py instantiate --pack runs/creddata-auto-v3-fullfile/templates \
  --task all --seed bilingual-check-01 --out runs/creddata-auto-v3-fullfile/instances/bilingual-check-01
python3 -B metric-detection/scripts/creddata_preflight.py --root runs/creddata-auto-v3-fullfile \
  --instances runs/creddata-auto-v3-fullfile/instances/bilingual-check-01 --all-candidates
```

`--per-family`는 작업군·지시문 언어별 기본 작업 수다(기본 25 → 기본 작업 100, 환경 200).
`--exclude ids.txt`(session id 한 줄에 하나)로 나중의 스캐너 기반 필터 등에서 파일을 뺄 수 있고, 목록의 해시가
tasks.json에 남는다. split·저장소·component는 `source_splits/creddata-v1`에서 상속한다(session id 동일).
그 manifest는 조각 변환을 해시하므로 파일 전체 입력은 `runs/creddata-source-fullfile/manifest_fullfile.json`으로
따로 기록·검사한다. tasks.json·templates/는 생성값과 무관하다. 적격성 판정은 원본과 고정된 probe 문자열만 쓴다.

### gold와 후보

gold 유형은 CredData Category 문자열이다(`gold_category_train.jsonl`). Category가 없는 span은 train에서 같은 값의
가장 흔한 Category를 받고(same_value), 그래도 없으면 저장된 모델 판정(opus)을 쓴다. NOT_A_CREDENTIAL·UNSURE와
검토한 template placeholder 6개는 dropped이며 정답이 아니므로 placeholder 없이 원문으로 남는다.
task.json의 slot은 `type`(Category), `coarse_type`(기존 5유형), `category_source`를 갖고, registry와 궤적 라벨의
span 유형도 Category다.

후보 조건: train, 1,000줄·100KB·gold 30개 이하, dropped가 아닌 gold가 모두 아래 자리 중 하나일 것.

| 자리 | 값을 쓰는 법 |
|---|---|
| `literal` 파싱하는 언어의 문자열 리터럴 전체 | 기존 escaping codec |
| `literal_part` 리터럴 일부(URL 속 비밀번호 등) | 같은 codec(YAML plain은 그대로), 양옆 구분자는 피함 |
| `raw_code` 주석·따옴표 없는 값 / `raw_text` 파싱하지 않는 형식(.md .txt .properties .conf …) | 그대로 삽입. 공백·따옴표·역슬래시·양옆 문자(URL 안이면 URL 구분자)는 피함. 자유 형식 값은 `<>&$%{}#;,\|*`도 피함 |
| `pem_block` PEM 개인키 | 생성한 키를 원본 배치(들여쓰기, 주석 접두어, 리터럴 `\n`, 따옴표로 이은 줄, 줄 폭)에 다시 배치 |
| `jwk_fields` JWK 조각 | 키 자료 필드만 필드별로 교체. 필드 순서·따옴표·줄 배치·kty/crv/크기 유지 |

값은 slot(원본 값 + Category)마다 하나다. 고정 형식은 `creddata_category_formats.generator_for`로 만들어 그대로 쓰고
(문맥 문자와 겹치면 통째로 다시 뽑는다), 그 외는 `creddata_category_profiles.generate(..., avoid=…)`로 만든다.
고정 형식의 문자가 그 자리의 구분자와 겹치면(예: base64 Basic 값이 URL userinfo에) 파일을 제외한다.
처리할 수 없는 gold가 하나라도 있으면 파일을 사유와 함께 제외하며 임의로 고치지 않는다.

2026-11-16 빌드: gold가 있는 train 파일 2,847개(전부 dropped 2개) → 제한 이내 2,605개 → 후보 2,307개(245저장소).
제외 사유: 1,000줄 초과 221, 문맥 80자 미만 171, gold 값이 placeholder 밖에도 남음 38, 리터럴 경계를 넘는 gold 24,
label 규칙이 자리를 거절 19, 100KB 초과 2, gold 30개 초과 17, PEM 헤더 12, gold span 겹침 11, 고정 형식-문맥 충돌 7,
PEM 생략("...") 4, 기타 PEM·JWK·escape 12. 작업군별 후보: 분석·문서 2,307, 리팩터링 796, 테스트 324.
제한 이내 파일의 PEM span 262개 중 232개, JWK span 41개 중 34개를 다시 배치할 수 있었다(나머지는 헤더·생략·
객체를 넘는 span 등).

### 검증

`creddata_preflight.py`는 tasks.json에 `source_scope: whole_file`이 있으면 파일 전체 검사를 한다. 템플릿이 원본 파일
전체를 복원하는지, placeholder가 dropped가 아닌 gold와 정확히 일치하는지, 한영 쌍의 바이트·값, registry span 디코드,
결정성에 더해 (i) 값이 Category에 맞는지(고정 형식은 `conforms`, 자유 형식은 프로필 존재와 피할 문자),
(ii) 원래 구문이 완결된 파일이 주입 후에도 완결인지, (iii) 값을 넣은 파일을 그대로, Read 도구처럼 줄 번호(오른쪽 정렬
번호와 탭)를 붙여, `grep -n`처럼 `N:`을 붙여 도구 출력 한 건으로 라벨러에 넣었을 때 알려진 span이 모두 같은 범위·
Category로 라벨되는지 본다. `--all-candidates`는 선택하지 않은 후보 전체에 같은 값 생성·적합성·구문·투영 검사를 하고
`candidates_check.json`에 재추첨 횟수를 Category·자리별로 남긴다.

줄 번호가 붙은 도구 출력은(모든 줄의 번호가 증가할 때만) 번호를 떼고 라벨한 뒤 원래 좌표로 되돌린다. 여러 줄에 걸친
값(PEM, JWK)은 첫 글자부터 마지막 글자까지 한 span이며 사이의 줄 번호도 span 안에 든다. 이 처리는 v3 작업에만
적용하며 기존 카탈로그와 convert_trajectory.py의 동작은 그대로다.

기존 재추첨 검사(label_rules.judge_occurrence, 최대 16회)는 단일 값 자리에 유지하고, 라벨러 투영(정확한 범위)과
구문 유지도 함께 본다. 재추첨은 거절된 slot만 한다. PEM·JWK 블록에는 judge_occurrence가 맞지 않으므로(라벨러는 알려진
블록을 그대로 찾는다) 대신 PEM armor·본문 검사와 `conforms`, 세 가지 투영으로 확인한다.

2026-11-16 `bilingual-check-01`: preflight 통과(환경 200, span 536, 세 투영 모두 누락 0), `--all-candidates` 통과
(후보 2,307개 전부 값 생성·적합성·구문·투영 통과).

한계: 알려진 dropped 아닌 gold만 다룬다(라벨 완전성 아님). 생성값은 원본 애플리케이션의 의미를 보존하지 않는다
(PEM armor 종류는 생성기 분포를 따르고, JWK 수치는 합성값이다). Read 도구가 2,000자를 넘는 줄을 자르는 등 실제
도구 출력의 다른 형식은 검사하지 않는다. 자유 형식 값이 문맥 문자를 피하므로 원본보다 기호가 적을 수 있다.

## 대량 실행과 학습용 인계 파일 (v3-r2)

`creddata-auto-v3-fullfile-r2`는 v3 후보에서 스캐너 필터로 15개 파일을 뺀 뒤 작업군·지시문 언어별 200개씩 뽑은
카탈로그다(기본 작업 800, 환경 1,600, 원본 파일 800, 저장소 224, component 207). 산출물은 전부 `runs/` 아래에 있고
git에 넣지 않는다.

```bash
# 1. 스캐너 필터: 아무도 판정하지 않은 줄에 gitleaks·CredSweeper가 무언가를 찾은 파일을 뺀다
#    (필터 없이 만든 카탈로그의 eligibility.jsonl이 입력)
python3 -B metric-detection/scripts/creddata_scan_filter.py
# 2. 필터를 적용한 카탈로그와 값 주입
python3 -B metric-detection/scripts/creddata_fullfile.py build --per-family 200 \
  --exclude runs/creddata-source-fullfile/scanner_filter/exclude.txt \
  --version creddata-auto-v3-fullfile-r2 --out runs/creddata-auto-v3-fullfile-r2
python3 -B metric-detection/scripts/creddata_tasks.py instantiate --pack runs/creddata-auto-v3-fullfile-r2/templates \
  --task all --seed run-01 --out runs/creddata-auto-v3-fullfile-r2/instances/run-01
# 3. 대량 실행 (재개 가능, <instances>/STOP 파일을 만들면 진행 중인 실행만 끝내고 멈춘다)
python3 -B metric-detection/scripts/creddata_bulk.py --instances runs/creddata-auto-v3-fullfile-r2/instances/run-01 \
  --api-cap 170 --workers 4
# 4. 다시 라벨링, 값 치환 증강, 식별자 정제, 인계 파일 쓰기
python3 -B metric-detection/scripts/creddata_export.py --catalog runs/creddata-auto-v3-fullfile-r2 \
  --instances runs/creddata-auto-v3-fullfile-r2/instances/run-01 --out runs/creddata-trajectory-handoff/v1
```

### 스캐너 필터 (`creddata_scan_filter.py`)

파일 전체에는 CredData가 라벨하지 않은 줄이 많고, 거기에 있는 자격증명은 gold가 없어 음성으로 학습된다. CredData
라벨 행(판정 종류 무관)이나 우리 판정 span이 없는 줄에서 스캐너가 무언가를 찾으면 그 파일을 뺀다. 자동으로 라벨하지
않으며, 스캐너가 보고한 값은 기록하지 않는다. gitleaks 8.30.1, CredSweeper 1.19.0으로 후보 2,307개를 검사해 15개를
뺐다(전부 gitleaks: generic-api-key 71건, kubernetes-secret-yaml 4, curl-auth-user 2, private-key 2). 위험을 줄일
뿐 라벨 완전성을 보장하지 않는다.

### 대량 실행 (`creddata_bulk.py`)

실행마다 구독 계정의 5시간·주간 사용률을 읽어 `--switch-at`(기본 95%) 미만이면 계정으로, 그 이상이거나 한도 오류로
끝난 뒤에는 한도가 풀릴 때까지 API 키(`--env-file`, 기본 저장소 루트의 `.env`)로 실행한다. API 지출 합계가
`--api-cap`에 닿으면 API를 쓰지 않고 기다린다. 끝나지 못한 실행은 `attempts/`로 옮기고 한 번 더 시도하며, 8번
연속으로 끝나지 못하면 중단한다. 기록은 `<instances>/bulk.log`에 남고 토큰·키는 기록하지 않는다. 기본값은
`claude-sonnet-5-5`, effort high, 실행당 예산 1 USD, 제한 시간 900초, 계정 설정 폴더 `~/.claude-trajectory`다.

에이전트는 `~/workspaces/project-XXXX`(환경 변수 `CREDDATA_WORK_BASE`로 변경)로 복사한 작업 폴더에서 실행하고,
끝난 뒤의 폴더는 `workspace_after/`에 남긴다. 작업 폴더 경로에 데이터셋 이름이나 `private/`가 드러나지 않게 하기
위해서다.

2026-11-16 `run-01`: 1,600개 중 1,599개 종료, 1개 미완료. 구독 계정 195개, API 1,405개(98.87 USD).

### 여러 줄 키의 라벨 (`creddata_rollout.py`)

PEM·JWK 값은 도구 출력에서 줄 번호, `cat -A`의 줄 끝 `$`, JSON escape, 다시 접힌 줄, 일부 줄만 있는 형태로 나온다.
정확한 형태가 맞지 않으면 텍스트의 토큰을 키의 base64 스트림에 정렬해 찾는다(`how`는 `stream` 또는
`stream_partial`, `coverage`에 덮은 비율, 규칙 `known_key_stream`). armor 줄만 있거나 다른 키인 경우는 라벨하지
않는다. 검사는 `test_creddata_key_streams.py`에 있다.

### 인계 파일 (`creddata_export.py`)

끝난 실행을 현재 라벨러로 다시 라벨하고(instance의 `labeled/`는 실행 당시 그대로 둔다), 궤적마다 `--variants`(기본
2)개의 값 치환 사본을 만든다. 사본은 주입한 값이 나타난 자리를 같은 slot의 새 값으로, 같은 표기 형태로 바꾼 것이며,
새 값으로 처음부터 라벨한 결과가 바꾼 span과 정확히 같을 때만 남긴다. gold가 없는 궤적은 음성으로 한 번만 넣는다.
모든 행은 원본의 split과 component(`group_id`)를 상속한다.

라벨 전에 실행한 계정·머신의 식별자(계정 이메일, 사용자 이름이 든 경로, Python 환경 이름, 설정 폴더 이름)를 중립적인
이름으로 바꾼다. 에이전트가 작업 폴더 밖의 CredData 사본에 닿은 실행과, 치환으로 라벨이 달라진 실행은 뺀다.

출력: `sessions_train.jsonl`, `gold_train.jsonl`, `labels_train.jsonl`, `manifest.json`. `--out`은 `runs/` 아래여야
한다(라이선스가 있는 원본 텍스트와 생성한 비밀값이 들어 있다).

2026-11-16 `runs/creddata-trajectory-handoff/v1`:

| | 궤적 | gold span |
|---|---|---|
| 기록된 궤적 | 1,594 | 5,195 |
| 값 치환 사본 | 2,967 | 9,445 |
| 합계 | 4,561 | 14,640 |

제외한 실행 6개(미완료 1, 작업 폴더 밖으로 나감 5). 버린 사본 199개(다시 라벨한 결과가 다름 107, span이 값 하나의
표기가 아님 62, 스트림 정렬로 찾은 키 24, 원본 배치를 찾지 못함 6). 기록된 궤적은 작업군 × 지시문 언어마다
198~200개이고, gold가 없는 기록된 궤적은 11개다.

한계: 주입한 값만 라벨한다(라벨 완전성 아님). 값에서 파생된 출력(`wc`, `openssl` 결과 등)은 라벨하지 않고 사본에서도
바꾸지 않는다. 전부 CredData train 구획에서 나왔으므로 component를 나누거나 무작위로 다시 분할하지 않으며, 기록된
궤적과 그 사본은 같은 fold에 둔다. 이 데이터로 학습한 모델은 CredData 전체를 독립 평가로 보고할 수 없다. 원본
저장소마다 라이선스가 다르므로 외부에 공개하기 전에 확인이 필요하다.
