# secret-sources: 코딩 에이전트 시크릿 출처 마스터 카탈로그

코딩 에이전트가 주고받는 텍스트에서 비밀값을 '문맥'으로 찾아 가리도록 SLM을 학습시키기 위한
**출처 카탈로그**(`coding_agent_secret_sources_master_v3.csv`, 613행 × 15열)를 결정적으로 생성한다.
한 행은 하나의 고유 시크릿 유형 또는 하나의 고유 코딩/에이전트 맥락이다.

CSV 자체는 git에 올리지 않는다(`.gitignore`). 예시 열의 비밀값이 실제 포맷(접두사·길이·체크섬)을 따르는
가짜 값이라 GitHub push protection이 진짜 비밀로 보고 막기 때문이다. 다른 metric-detection 합성 데이터와
같은 방침이다. 생성은 결정적이므로 누가 돌려도 바이트 단위로 같은 파일이 나온다.

## 생성

```bash
cd metric-detection/secret-sources
python3 build_v3.py coding_agent_secret_sources_master_v3.csv
```

- 저장: `quoting=csv.QUOTE_ALL`, `encoding="utf-8-sig"`.
- 값: `v3_engine.py`의 `shake_256` 스트림에서 공개 규칙으로 만든 가짜 값. 인증에 쓸 수 없다.
- 빌드 끝에 검증(결측치 0, Positive 전부 고유, 정규식 자가검증, NUL 바이트 없음)을 자동으로 돌린다.

## 15열 스키마

`Source_ID, Macro_Category, Sub_Category, Reference_Benchmark_or_Repo, Source_Description_KR,
Typical_File_Paths_or_Streams, Agent_Acquisition_Channel, Data_Format_or_Syntax, Asset_or_Host_Pair_Context,
Key_Identifiers_and_Indicators, Regex_or_Structural_Signature, Synthetic_Positive_Example_Raw,
Hard_Negative_Counterpart_Example, Risk_Severity, SLM_Training_Guideline_KR`

## 파일

| 파일 | 역할 |
|---|---|
| `build_v3.py` | 엔트리포인트. 데이터 모듈을 모아 `ROWS`를 채우고 검증 후 CSV로 쓴다. `pfx()`(접두사 토큰)·`add()`(자유형) 헬퍼와 검증(`_validate`)이 여기 있다 |
| `v3_engine.py` | 결정적 가짜 값 생성기(토큰·JWT·PEM·비밀번호·UUID와 플레이스홀더/참조/EXAMPLE 음성값) |
| `v3_render.py` | 문맥 렌더러: `(변수, 값)`을 .env·yaml·json·py·js·java·curl·헤더·터미널·git diff·MCP·raw 등 2~6줄 스니펫으로 |
| `v3_data_services.py`, `v3_data_services_more.py` | 카테고리 01~11,13의 서비스/토큰 유형 행(제네릭, AI/LLM/MCP, 클라우드, DB, VCS/패키지, 시크릿 매니저, 엔터프라이즈, 핀테크, 메시징, 관측, 크립토, 모바일/Web3) |
| `v3_data_agent.py` | 카테고리 12: ANSI 터미널, 언어 AST/폴백, 툴 호출→결과 멀티턴, `/proc/environ`, MCP JSON-RPC, 스택트레이스, HAR, Jupyter, 소스맵 등 런타임 맥락 |
| `v3_data_supp.py`, `v3_data_supp2.py`, `v3_data_supp3.py` | 보강: KR/아시아 거래소·간편결제·소셜 인증, DB 스킴, 개발도구 자격증명 파일(.npmrc·.pgpass·kubeconfig·.m2 등), 추가 SaaS 토큰 유형 |
| `v3_data_auto.py` | 스캐너 카탈로그 인덱스에서 접두사 토큰 규칙을 자동 추출해 롱테일 서비스를 확장(인덱스가 있을 때만) |
| `index_rules.py`, `index_disc.py` | 스캐너 레포 트리를 통합 룰 인덱스(JSON)로 파싱 |
| `rules_slim.json`, `rules_disc_slim.json` | 위 인덱스의 경량본(정규식·이름·출처만, 스캐너 예시 토큰은 제거). `v3_data_auto.py`가 읽는다 |

## 출처

seed 스캐너/벤치마크 14종(gitleaks, trufflehog, noseyparker, Samsung CredData/CredSweeper, nuclei-templates,
semgrep-rules, whispers, detect-secrets, secrets-patterns-db, mongodb/kingfisher, talisman, shhgit, ripsecrets,
OWASP WrongSecrets)에 더해, 자율 탐색으로 찾은 신규 출처 22종을 반영했다: secretlint, betterleaks,
google/osv-scalibr(Veles), gitlab-org secret-detection-rules, github/docs partner patterns,
microsoft/security-utilities, awslabs/git-secrets, bridgecrewio/checkov, avito-tech/deepsecrets,
그리고 공식 벤더 SDK/문서(koreainvestment/open-trading-api, tosspayments, portone, solapi, pyupbit,
line-bot-sdk, larksuite, tencentcloud-sdk, dashscope, zhipuai, dingtalk, bootpay, developers.kakao,
CLOVA Studio, naver, data.go.kr).

`rules_slim.json`을 다시 만들려면 각 스캐너 레포를 받은 뒤:

```bash
python3 index_rules.py <스캐너_레포_루트> rules.json       # seed 14종
python3 index_disc.py  <신규_출처_레포_루트> rules_disc.json  # 신규 9종(레포형)
# 커밋용 경량본: examples/negatives 필드를 비워 rules_slim.json / rules_disc_slim.json 생성
```

인덱스가 없으면 `build_v3.py`는 auto 확장(약 156행)을 건너뛰고 457행을 만든다(최소치 400 충족).
