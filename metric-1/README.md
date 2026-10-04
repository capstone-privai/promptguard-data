# PromptGuard 지표 1 최소 테스트셋 v0.1

**1단계의 task 무관 마스킹을 확인하는 합성 세션 초안**이다. 12개 세션, 51개 입력, 정답 span 32개로 기존 평가기를 바로 실행할 수 있다. 실제 Codex rollout을 수집하거나 재생한 데이터는 아니다. 이번 버전은 형식 연결과 실패 유형 확인용이며 최종 성능 벤치마크가 아니다.

## 빠르게 검토하기

- `REVIEW.md`: 12개 세션의 원문과 MASK/KEEP 위치를 펼쳐서 읽는 문서.
- `sessions.jsonl`: **평가기 입력**. 한 줄이 세션 하나이며 `items`와 `gold`가 함께 들어 있다.
- `annotations.jsonl`: 사람이 검토하기 위한 주입 기록. 값, 정확한 위치, MASK/KEEP, 이유, 노출 형태를 보관한다. 평가기에는 넘기지 않는다.
- `manifest.json`: 구성표와 고정 데이터 SHA-256.
- `item_provenance.jsonl`: 출력이 발생할 법한 명령과 합성 출처. 명령은 실제 실행하지 않았다.
- `carrier_review.jsonl`, `carrier_scan.json`: 비밀 슬롯을 제거한 바탕 텍스트와 누락 검사 결과.
- `validation.json`, `checks/`: 정합성 검사와 기존 평가기의 실행 결과.

## 범위와 출처

기준 브랜치의 실제 이름은 `feat/evaluation-metric1`이다. 참조 커밋은 `027a3e0d0cb4d86e9b310293229dddc7d4459b9c`이다. 기존 `evaluation/`와 `promptguard/` 코드는 바꾸지 않았다.

1. [확정된 시스템 평가 지표](https://app.notion.com/p/3efe12506fbd80e2b7b3d75580fb36d8), [지표 1 상세](https://app.notion.com/p/3efe12506fbd80abb627dba21eb437b4): 세션 구조, 독립된 정답, 주입 생성, 엄격 span 보호율, 실제 처리 채널만 통과시키는 기준.
2. [정우 담당 작업 / 2026-10-02 라벨 결정](https://app.notion.com/p/3ebe12506fbd817c9aeff7afeb5ad3d3): 테스트 값·공개용 키·약한 기본 비밀번호도 MASK, 연결 문자열 전체를 한 단위로 보는 기준.
3. [공유 Claude 대화](https://claude.ai/share/88dd39e6-b076-4e2d-a592-4defadfe9340): 설정·로그·명령줄·Git 이력 등 노출 위치 다양화, 반복 노출과 인코딩, 어려운 음성 필요성을 반영했다. 대화의 첨부 키트를 가져오거나 그 안의 5세션·140개 span을 재사용한 것은 아니다. 대화에 인용된 외부 연구 수치도 이번 데이터의 근거 수치로 사용하지 않는다.
4. [평가 브랜치 README](https://github.com/capstone-privai/promptguard-demo-v0/blob/027a3e0d0cb4d86e9b310293229dddc7d4459b9c/evaluation/README.md): 입력 형식과 실행 명령.

외부 코퍼스 본문을 복사하지 않고 이번 작업에서 짧은 작업 맥락을 직접 작성했다. 비밀은 공개된 결정적 생성 규칙으로 만든 합성값이며 서비스에서 발급받거나 사용한 값이 없다. PEM도 등록되지 않은 테스트 키다. 제3자 데이터셋 라이선스는 상속하지 않으며, 신규 산출물에 별도 배포 라이선스는 지정하지 않았다.

## 12개 시나리오

| ID 끝자리 | 작업 맥락 | 확인할 점 |
|---|---|---|
| 01 | Node 환경 설정 | 따옴표 안 `#`, `.env.example`의 `changeme`, 변수 참조 |
| 02 | Python DB 오류 | TOML과 예외에 반복되는 연결 문자열 전체 |
| 03 | Docker Compose | `postgres` 기본 비밀번호, 명백한 테스트 토큰 |
| 04 | HTTP 인증 | Bearer, Basic base64, 세션 쿠키, UUID·ETag |
| 05 | Git 이력 | 삭제된 줄의 AWS 형식 키, 커밋 SHA |
| 06 | 프로세스 출력 | `mysql -p…`, 셸 기본값, 환경변수의 GitHub 형식 토큰 |
| 07 | Kubernetes | Secret data의 base64, URL 인코딩된 연결 문자열 |
| 08 | 프롬프트·AGENTS.md | 한국어·영어 자연어와 현재 미처리 채널 |
| 09 | 개인키 | 실제 파싱 가능한 Ed25519 PKCS8, 여러 줄 span |
| 10 | 빌드 출력 | 비밀 0개, lockfile 해시·이미지 digest·UUID |
| 11 | 설정 문서 | 비밀 0개, 변수 참조·미입력 자리표시·토큰 개수 |
| 12 | 키 교체 | 여러 턴, 동일 값의 여러 등장, 한국어·이모지·CRLF |

## 구성

| 항목 | 수 |
|---|---:|
| 세션 / 입력 | 12 / 51 |
| 정답 MASK span | 32 |
| 명시적으로 표시한 KEEP span | 17 |
| 비밀이 없는 세션 | 2 |
| 줄 수 | 151 |
| 비밀 밀도 / 1,000줄 | 211.92 |

| 정답 종류 | 수 |
|---|---:|
| PASSWORD | 14 |
| TOKEN | 7 |
| SECRET | 7 |
| ACCESS_KEY | 3 |
| PRIVATE_KEY | 1 |

| 채널 | 정답 수 | 현재 처리 |
|---|---:|---|
| stdout | 22 | 예 |
| stderr | 7 | 예 |
| prompt | 2 | 아니오 |
| agents_md | 1 | 아니오 |

`file_read`와 `mcp`는 레포에서 예약 채널이므로 이번 최소 버전에는 넣지 않았다. 프롬프트와 AGENTS.md의 3개는 전체 Recall 분모에 남는다. 현재 채널 구성만으로는 이 데이터에서 최대 보호율이 29/32 = 90.625%다. 도구 출력에서만 낸 Recall을 전체 점수로 바꿔 보고하면 안 된다.

KEEP 17개는 사람이 확인할 주요 구간에 대한 보조 표시이며 Precision의 분모가 아니다. 정답 span 밖의 **모든 글자**가 비밀 아닌 영역이다. 따라서 별도로 KEEP 표시하지 않은 줄 번호를 가려도 오탐으로 센다.

## 라벨 규칙과 충돌 해결

- `start` 포함, `end` 제외. JSON 파싱 후 `item.text`의 **Python Unicode 코드 포인트** 기준이다. UTF-8 바이트나 UTF-16 인덱스가 아니다. CRLF의 `\r`와 `\n`은 각 1자다. `REVIEW.md`의 `␍`는 가독성 표시일 뿐 정답 원문은 JSONL이다.
- 값 삽입 순간 위치를 기록한다. 탐지기 후보를 정답으로 승격하지 않는다. 중첩 span은 만들지 않는다.
- 같은 값이 한 항목에서 두 번 나오거나 다음 턴에 다시 나오면 각각 정답이다. 원본 rollout의 `event_msg`나 누적 요청 복사본은 만들지 않는다.
- 비밀번호는 값만, 따옴표·`Bearer `·`Basic `·쿠키 이름과 구분자는 제외한다. API 토큰의 공개 접두사는 값에 포함한다. PEM은 BEGIN/END 경계와 내부 줄바꿈을 포함하고 마지막 출력 개행은 제외한다.
- **연결 문자열은 URL 전체를 정답으로 채택했다.** 10/02 라벨 결정과 레포 예제의 ‘비밀번호 부분만’은 범위가 다르다. 이 초안에서는 라벨 결정을 우선한다. 현재 평가 스키마에 `URL_CREDENTIAL`이 없어 `SECRET`으로 매핑하고 보조 주입 기록의 `subtype`에 `URL_CREDENTIAL`을 보존한다. 비밀번호만 가린 두 URI는 이 정책에서 partial이다. 쿼리 문자열의 미확정 경계는 피했다.
- base64와 URL 인코딩은 되돌릴 수 있으므로 **표면에 표시된 인코딩 문자열 전체**를 정답으로 둔다. 디코딩 후 길이로 오프셋을 매기지 않는다. 이 확장 경계는 팀 검토 대상이다. 비밀을 나눈 조각, 해시 등 비가역 파생값, JWT와 코드 모드 래퍼는 v0에 포함하지 않았다.
- `dummy_token_123`, `test1234`, `changeme`, `postgres`, `pk_test_…`는 MASK다. `${DB_PASSWORD}`, `<API_TOKEN>`, 빈 값, SHA·UUID·ETag·토큰 개수는 KEEP다. 이유의 `real_credential`은 라벨 정책의 ‘사용 가능한 기본 비밀번호’ 범주를 뜻하며, 실제 계정에서 가져왔다는 뜻이 아니다.
- 메타데이터에는 원문 비밀값을 넣지 않는다. 값은 입력과 검토용 sidecar에만 있다.

## 재생성과 실행

데이터와 생성기는 이 저장소의 `metric-1/`에 있고, 평가기는 별도 [promptguard-demo-v0](https://github.com/capstone-privai/promptguard-demo-v0/tree/feat/evaluation-metric1)의 `feat/evaluation-metric1` 브랜치에 있다. 두 저장소를 같은 부모 폴더에 두는 예시다. Python 3.10 이상에서 생성할 수 있으며 이번 검증은 Python 3.12.14 / CredSweeper 1.18.5에서 실행했다.

이 데이터 저장소 루트에서:

```bash
# 생성만 할 때는 표준 라이브러리만 필요하다.
python metric-1/scripts/build_metric1_v0.py

# 평가기 저장소의 의존성이 설치된 Python 환경에서 실행한다.
python metric-1/scripts/verify_metric1_v0.py --evaluation-repo ../promptguard-demo-v0
python metric-1/scripts/verify_metric1_v0.py --evaluation-repo ../promptguard-demo-v0 --scan-carriers
```

평가기 저장소 루트에서:

```bash
python -m pip install -r requirements.txt
python -m evaluation validate --dataset ../promptguard-data/metric-1/sessions.jsonl
python -m evaluation run --dataset ../promptguard-data/metric-1/sessions.jsonl --system oracle
python -m evaluation run --dataset ../promptguard-data/metric-1/sessions.jsonl --system identity
python -m evaluation run --dataset ../promptguard-data/metric-1/sessions.jsonl --system promptguard
python -m evaluation run --dataset ../promptguard-data/metric-1/sessions.jsonl --system credsweeper --ml off
```

생성기의 기본 출력 위치는 작업 디렉터리와 무관하게 `metric-1/`이며 `--out PATH`로 변경할 수 있다. 검증기도 기본 데이터 위치는 `metric-1/`이고 `--dataset-dir PATH`로 바꿀 수 있다. `--evaluation-repo`에는 실제 평가기 저장소 경로를 지정한다.

`checks/`는 최초 실행 결과를 그대로 보존한 기록이다. 그 안의 `evaluation_data/metric1-v0/sessions.jsonl`은 **당시 실행 위치**이며, 현재 파일은 `metric-1/sessions.jsonl`이다. 데이터 해시는 동일하다. 새 실행 결과는 평가기 저장소의 `runs/`에 저장된다.

macOS에서 CredSweeper는 로컬 multiprocessing 통신을 사용하므로 이를 금지하는 실행 격리 환경에서는 실행이 막힐 수 있다. 모델 API나 실제 Codex 실행은 필요 없다.

## 검증과 최초 점검 결과

2026-10-04 검증: 원래 평가기의 스키마 검사, 모든 주입 span 문자열 대조, MASK/KEEP 비중첩, 긴 합성값의 모든 재등장 라벨 검사, 재생성 바이트 일치, SHA-256, PEM 파싱을 확인했다. 채점 실행마다 기존 평가기가 편집 목록과 실제 출력을 대조했다.

| 점검 시스템 | 완전 보호 | 부분 보호 | 놓침 | Recall | Precision |
|---|---:|---:|---:|---:|---:|
| Oracle | 32 | 0 | 0 | 1.0000 | 1.0000 |
| Identity | 0 | 0 | 32 | 0.0000 | N/A |
| PromptGuard + mock | 21 | 2 | 9 | 0.6563 | 0.6765 |
| CredSweeper, ML off | 21 | 2 | 9 | 0.6563 | 0.6765 |

실제 시스템 두 실행은 34개 치환 중 23개가 정답과 겹쳤고 11개는 오탐이었다. 같은 결과가 나온 것은 현재 mock이 모든 후보를 MASK하는 이 데이터에서의 관측이며, 학습된 판단기의 성능 비교가 아니다. 전체 32개 중 미처리 채널의 3개도 놓침에 포함되어 있다. 처리 채널에서 완전히 가린 수는 21/29다.

바탕 텍스트는 CredSweeper 한 도구로 검사했다. 16개 경보 중 5개는 제거한 주입 슬롯의 `<REDACTED>`, 11개는 UUID·줄 번호·키 식별자·토큰 개수였다. 에이전트가 원문 문맥과 대조했고, 남은 미분류 경보는 0개다. **여러 탐지기를 이용한 교차 검사와 사람의 최종 검수는 아직 하지 않았다.**

## 사용상 한계와 다음 단계

- 151줄에 32개 span으로 비밀 밀도가 높다. 이 Precision을 실제 사용 환경의 Precision으로 일반화하지 않는다.
- 템플릿을 직접 작성했고 종류 비율도 균등하지 않다. PRIVATE_KEY는 한 예뿐이다. 이 버전으로 PR 곡선이나 ML 개선 효과를 주장하기에는 작다.
- 모든 세션은 `pilot_test`, `human_review=pending`이다. 현재 정답은 고정된 제안이다. 팀 검토 후 버전·해시를 확정하고, 튜닝에 사용했다면 개발셋으로 재분류한 뒤 별도 최종 테스트셋을 마련한다.
- 값을 바꿔 행 수를 늘려도 같은 `group_id`는 한 분할에 묶어야 한다. 이번 12개 템플릿을 학습과 테스트 양쪽에 넣지 않는다.
- 다음 확장에서는 실제 Codex trace 또는 샌드박스 실행에서 얻은 바탕과 순서를 쓰고, 코드 모드·추가 비밀 종류·더 많은 비밀 없는 입력을 보충한다.

이 저장소에서는 `metric-1/`의 데이터·생성기·검토 문서·최초 점검 결과를 함께 버전 관리한다. 기존 후보 데이터 규격과 변환 도구는 루트의 `etc/`에 보관한다.
