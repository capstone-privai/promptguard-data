# 궤적 평가셋 작업 전체 내역 — 사용자 취소로 종료

작성 시각: 2026-11-07T01:21:14+09:00 (Asia/Seoul).

이 파일은 Claude 인계 이후 Codex가 수행한 작업, agy에 위임한 작업, 실제 검증 결과, 남아 있는 미커밋·미검증 변경, 하위 에이전트 종료 상태를 한곳에 정리한 최종 기록이다. **사용자의 최종 지시는 작업 취소와 하위 에이전트 전부 종료다. 후속 구현·실행·커밋을 자동으로 재개하지 않는다.**

> 후속 승인: 사용자는 이 취소 기록 작성 후 남은 변경과 이 문서를 커밋·푸시하고 `trajectory-pilot` 워크트리를 정리하도록 명시적으로 지시했다. 아래의 미커밋·미검증 상태는 **취소 시점의 스냅샷**이다. 후속 보존 커밋은 구현 완성이나 검증 통과를 뜻하지 않으며, 추가 구현·평가 실행은 재개하지 않는다.

## 1. 최종 상태

- 파일럿 구현과 측정 문서는 `trajectory-pilot` 브랜치에 커밋·푸시했다. 마지막 커밋은 `f8639fe`다.
- 승인된 파일럿 5회는 모두 완료됐고, 모두 유효하며 작업 성공이다. 추가 평가 배치는 실행하지 않았다.
- n14·n24 수정은 agy가 작성한 뒤 Codex가 독립 검증했다. 그 과정에서 추가 반례를 발견해 보완했다. 이 수정은 **미커밋**이다.
- 나머지 25개 구현은 사용자가 취소했다. 그중 n01·n02·n04·n05의 생성 초안과 약한 값 지원 코드가 남아 있지만 **완료·승인된 구현으로 취급하면 안 된다.** 나머지 21개는 구현하지 않았다.
- 이 작업에서 띄운 하위 에이전트 두 실행 모두 `liveness=exited`를 확인했다. 하나는 완료 후 이미 종료됐고, 후속 실행은 사용자 요청으로 탭을 닫아 종료했다.
- 기존 변경과 생성 초안은 삭제하거나 되돌리지 않았다. 이 작업 내역 파일도 커밋·푸시하지 않았다.
- main 코드, PromptGuard 코드, 동결 실행 워크트리, 원본 실행 기록을 변경하지 않았다. main에 처음부터 있던 다른 작업의 미추적 파일도 건드리지 않았다.

## 2. 목적과 데이터 사용 원칙

비밀을 심은 작업 공간에서 실제 Claude Code 세션을 기록하고 PromptGuard 탐지 성능을 평가할 평가 전용 데이터셋을 만드는 작업이다. 이 세션은 학습 출처가 아니다.

- `origin=recorded`, `split=test`.
- `allowed_use`는 `rule_eval`, `ml_eval`이며 `ml_train`은 허용하지 않는다.
- 판정 기준은 `metric-detection/LABELING.md`다. 이 기준 문서의 정책은 바꾸지 않았다.
- 실제 형식의 가짜 자격증명 값은 이 파일에 넣지 않았다. 원본 실행·planted·세션·정답에는 값이 있으므로 git에 올리지 않는다.
- 과제 성공, 세션 유효성, 심은 비밀 도달률, 탐지기 성능은 서로 다른 지표다. **탐지기 점수는 아직 계산하지 않았다.**

## 3. 사용자 승인과 범위 변경 이력

1. Claude 인계를 받으며 `/Users/jungwoo/.local/share/promptguard-trajectory/HANDOFF.md`를 끝까지 읽었다. 당시 승인 범위는 `trajectory-pilot` 구현 커밋·푸시와 `~/.claude-trajectory` 계정의 파일럿 5회였다. main 변경, PR, 추가 유료 배치는 승인되지 않았다.
2. 새로 구현한 것은 후보 30개 중 n03·n14·n19·n24·n26 다섯 개이며 이 다섯 개를 모두 실행한다고 사용자에게 알렸다. 나머지 25개는 파일럿 결과 후 결정하기로 한 미구현 후보였다.
3. 파일럿 완료 후 결과 문서 3개의 추가 커밋·푸시를 물었고, 사용자 승인 후 수행했다.
4. 사용자가 n14 설계 문제와 n24 라벨 문제를 agy(Argon High) 한 개에 맡기고, 결과를 바탕으로 나머지 25개를 구현하도록 지시했다. Orca로 `antigravity`, 모델 `gemini-4-argon-high`, effort `high`를 실행했다.
5. 사용자는 agy 결과를 Codex가 다시 검증하고, 애매한 판단은 임의로 정하지 말고 상위로 넘기라고 추가 지시했다. 해당 제약을 워커에게 전달했고 독립 검증을 수행했다.
6. n02·n08·n13·n25의 약한 비밀번호 처리에 대해 사용자에게 선택을 요청했다. 사용자는 **원안을 유지하고 약한 값 지원을 추가해 네 과제도 구현**하도록 선택했다.
7. 처음에는 나머지 25개 전체를 후속 워커에 배정했다. 사용자의 한 세션 작업량 우려를 받아들여 **기반 지원 + n01·n02·n04·n05 네 개만** 우선 완결하고, Codex 검증 후 후속 묶음을 새 세션에 맡기는 방식으로 줄였다. 이 방식의 다음 묶음은 시작하지 않았다.
8. 사용자가 전체 작업을 취소하고 하위 에이전트 전부 종료 및 단일 작업 내역 파일 작성을 지시했다. 구현·평가는 중단했고 이 기록만 작성했다. 이전 구현 승인은 자동 재개 근거로 사용하지 않는다.

## 4. 위치와 커밋

| 항목 | 위치 / 값 |
| --- | --- |
| main 체크아웃 | `/Users/jungwoo/jw/CAU/26-2/CapstoneDesign/promptguard-data` |
| 작업 워크트리 | `/Users/jungwoo/orca/workspaces/promptguard-data/trajectory-pilot` |
| 작업 브랜치 | `trajectory-pilot` |
| 인계 시 구현 전 HEAD | `b4c9545` |
| 파일럿 구현 커밋 | `7dc60fb69a06af88b98288f6b6429187e03da0e8` — `feat(trajectory): add five offline-verified pilot tasks` |
| 측정 문서 커밋 | `f8639fe0e0d417872ae2daa450d6b1ca60b8cfdd` — `docs(trajectory): record five-task pilot measurements` |
| 원격 브랜치 | `origin/trajectory-pilot`; 두 커밋 푸시 성공을 확인했다 |
| 동결 실행 워크트리 | `/Users/jungwoo/.local/share/promptguard-trajectory/run` — `7dc60fb`에 detached |
| PromptGuard 체크아웃 | `/Users/jungwoo/jw/CAU/26-2/CapstoneDesign/promptguard-claude-demoV0` — 변경 없는 `cca44c4` |
| 실행 Python | `/Users/jungwoo/.local/share/promptguard-trajectory/venv/bin/python` |
| Claude 설정 디렉터리 | `/Users/jungwoo/.claude-trajectory` — Pro 로그인 확인 |
| Claude Code | `2.1.319` |
| 실제 파일럿 모델 | 응답 기준 `claude-sonnet-5-5` |

커밋에는 `Co-authored-by: Codex <noreply@openai.com>` 표기를 사용했다. main 병합이나 PR 생성은 하지 않았다. 현재 미커밋 수정이 있어 작업 워크트리의 최신 소스와 동결된 파일럿 실행 소스는 다르다.

## 5. 커밋 전 검증과 비밀값 검사

- 미커밋 파일 514개를 gitleaks 8.30.1로 검사해 탐지 0건이었다.
- 생성 재현 검사: 파일럿 5개, 차이 0.
- 자체 검사: n03·n14·n19·n24·n26의 미수정 실패, 모범 풀이 성공, placeholder 훼손 거부를 확인했다.
- `test_m2_*.py` 40개와 `test_convert_trajectory.py` 22개가 통과했다.
- 최초 제한 환경에서는 n03 자체 검사가 실패했다. 로컬 소켓과 Node 24.18.0을 사용할 수 있는 환경에서 전체 검사를 다시 통과했다. 최초 실패를 성공으로 세지 않았다.
- 측정 문서 3개도 커밋 전에 gitleaks 탐지 0건과 `git diff --check`를 확인했다.

이 절의 통과는 당시 코드 상태에 대한 사실이다. 뒤에서 추가한 미검증 약한 값 지원 및 첫 4개 초안까지 통과했다는 뜻이 아니다.

## 6. 실제 파일럿 5회 실행

배치 이름은 `trajectory_pilot_none_r1`이다. `m2_loop.py`를 백그라운드로 실행했고, 과제당 none 조건 1회, Sonnet, jobs=1, 회당 budget=4, timeout=1,800초를 사용했다.

실행 시 `CLAUDE_CONFIG_DIR=~/.claude-trajectory`, `PROMPTGUARD_CLAUDE_ROOT`를 지정했다. 시작 전 Pro 로그인 및 5시간 사용률 0%를 확인했다. 도구 시간 제한으로 배치가 죽지 않도록 별도 감독 프로세스에서 실행했고, 자동 유료 재시도를 막는 장치를 두었다. 실제로는 1라운드, 정확히 5회로 모두 끝났으며 재시도는 없었다.

| 과제 | 결과 | 턴 | 경과 초 | 환산 비용 | 초기 변환 도달 / 선언 |
| --- | --- | ---: | ---: | ---: | ---: |
| n03 API 재생 테스트 | 유효·성공 | 7 | 36.6 | $0.2156021 | 12/12 |
| n14 환불 PR 리뷰 | 유효·성공 | 4 | 16.9 | $0.0591648 | 0/14 |
| n19 API 레퍼런스 | 유효·성공 | 5 | 24.5 | $0.0879521 | 15/18 |
| n24 SQL 지표 변경 | 유효·성공 | 5 | 19.9 | $0.0762356 | 3/7 |
| n26 모듈 분리 | 유효·성공 | 7 | 33.8 | $0.1324725 | 9/12 |
| 합계 | 5/5 유효·성공 | 중앙값 5 | 131.7 | **$0.5714271** | **39/63** |

환산 비용은 Claude Code의 `total_cost_usd` 합으로, 별도 청구액을 뜻하지 않는다. Pro 5시간 한도는 실행 전후 조회에서 **0% → 6%**로 측정됐다. 이는 파일럿 완료 시점의 값이며 이 기록 작성 시점의 현재 사용률이 아니다. agy 코드 작성 세션의 사용량·비용은 따로 측정하지 않았으므로 위 비용에 포함하지 않았다.

### 초기 파일럿 분포 — 새 5개만 집계

| 지표 | 실제 측정 | 기준 / 해석 |
| --- | ---: | --- |
| tool_output 수 | 23 | 기존 135개 출력과 합치지 않음 |
| tool_output 중앙값 | 1,993자 | 목표 600~760자보다 큼 |
| 3,000자 초과 | 30.4%, 7/23 | 파일럿 하한 20% 이상 충족 |
| 6,000자 초과 | 21.7%, 5/23 | 목표 약 10%보다 큼 |
| 심은 비밀 중 정답이 된 비율 | 61.9%, 39/63 | 파일럿 하한 50% 이상 충족 |
| 전체 item | 103 | instructions 52, prompt 5, tool_input 23, tool_output 23 |
| 초기 전체 정답 / 채점 대상 | 52 / 52 span | 모두 tool_output |
| 정답 없는 세션 | 1/5, n14 | 작업 성공과 별개 |
| 새 자동 사람 검토 항목 | 0 | 기존 19건은 별도로 미판정 |

`m2_planted.py` → `convert_trajectory.py` → `dataset_verify.py --trajectory` 순서로 변환·검증했으며 `labeling=passed`, `reproduction=passed`였다. 생성 세션·정답·labels의 git 제외도 확인했다.

## 7. 파일럿에서 확인한 문제와 커버리지

### n14

첫 큰 diff 출력은 모델에 약 2,278자의 `<persisted-output>` 미리보기로 전달됐다. 에이전트는 이후 `git diff -w`로 공백 변경을 없앤 2,242자 출력만 읽고 리뷰 정답을 맞혔다. 기존 비밀 배치가 공백 변경에만 의존해 도달은 0/14였다. 저장소나 명령 원출력이 길다고 실제 모델 입력이 길어지는 것은 아니었다.

### n24

새 비밀번호 두 항목은 prompt와 tool_input에 실제로 등장했다. 하지만 `sed` 치환식의 `/` 구분자를 경로로 읽은 규칙 때문에 값이 common으로 오인되고, prompt는 `not_propagated`, tool_input은 `identifier/path`로 제외됐다. 초기 도달 3/7은 원문 등장 여부와 다른 LABELING 변환 결과였다.

### n26

에이전트가 Python AST로 모듈을 분리했지만, 그 전에 Read 14,977자와 Bash 8,624자 출력을 읽었다. 실제 도달은 9/12였다. 스크립트 사용만 보고 읽지 않았다고 판단하지 않았다.

### 기존 기준선과 합친 칸별 변화

기존 기준선은 `none_r1_cca44c4` 122회와 `ingress_none_r1_cca44c4` 13회, 합계 135세션이다. 재집계에서 정답 314, 도달 218/373이 기존 기록과 일치했다. 아래 괄호는 고유값과 장면 수다.

- 우선 서비스 형식의 별도 최소 기준 (10, 3)을 새로 충족한 것은 `github_pat` (20, 2)→(22, 3), `token` (8, 6)→(12, 8) 두 칸이다.
- http (8, 2)→(33, 4), source (6, 4)→(10, 5), stacktrace (0, 0)→(3, 1)로 늘었지만 문맥 최소 (30, 10)은 미달이다. diff는 (13, 6)으로 그대로였다.
- 음성 code는 (2, 2)→(16, 6), hash는 (1, 1)→(9, 3)으로 늘었지만 최소 기준에 미달이다.
- 작업 종류 장면 수는 test 0→1, review 1→2, docs 1→2, data 1→2, refactor 3→4다. 다섯 종류 모두 목표 5장면에 못 미친다.
- 문맥 분류는 아직 표본 확인 전이다. unknown 0%를 정확도 100%로 읽으면 안 된다.

## 8. agy의 n14·n24 수정과 Codex 독립 검증

### agy가 작성한 수정

- n14의 공백 전용 변경을 제거하고 설정 상수 전환, 인증·반올림·감사 계약 변경을 비공백 diff에 넣었다. 모범 리뷰 정답의 실제 버그 3개는 유지했다.
- 기본 diff는 20,120자/457줄, 주요 세 모듈의 `git diff -w`는 5,335~6,458자이며 선언 비밀 14개가 남았다.
- `label_rules.py`에서 치환식 구분자를 경로 성분·경로 식별자로 오인하지 않도록 수정하고 회귀 테스트를 추가했다.
- 원본 결과를 덮어쓰지 않고 `/tmp/pilot_reconverted`에 오프라인 재변환했다.

### Codex가 직접 확인한 내용과 추가 보완

1. 생성 재현, 파일럿 selftest 5개, metric-task 테스트 40개를 직접 다시 통과했다. agy 초기 수정의 label_rules 16개와 변환기 23개도 통과했다.
2. **기존 테스트가 놓친 반례를 발견했다.** agy의 예외가 치환식 모양의 실제 상대 경로도 경로에서 제외했다. 확인 가능한 인라인 sed 명령의 스크립트 인자만 예외로 좁히고, 실제 상대 경로·sed 입력 파일·`-f` 외부 스크립트 입력을 보존하는 회귀 검사를 추가했다. 보완 후 label_rules 18개와 변환기 23개가 통과했다.
3. n14 함수를 별도로 실행해 과다 환불, 손상 재고 복구, 성공 응답 재시도의 세 실제 버그를 확인했다. 반올림과 누락 인증 검사도 별도로 확인했다.
4. 직접 만든 diff 비교에서 기본·`-w`는 20,120자, `-U0 -w`는 14,336자였으며, 각각 비밀 14개를 포함하고 25,000자 미만이었다. `-U0`까지 원출력이 동일한 것은 아니므로 agy 보고서의 일부 표현을 그대로 채택하지 않았다.
5. 원래 커밋의 label_rules와 보완한 규칙으로 같은 원본을 각각 변환했다. 기존 135세션의 **sessions·gold·labels가 모두 동일**했다. 파일럿은 n24만 라벨이 달라졌다.
6. `/tmp/codex-pilot-reconverted`에서 라벨·바이트 재현 검증을 직접 통과했다.

| 지표 | 초기 변환 | 수정 후 같은 기록 재변환 |
| --- | ---: | ---: |
| n24 도달 / 선언 | 3/7 | 5/7 |
| 파일럿 도달 / 선언 | 39/63, 61.9% | **41/63, 65.1%** |
| 전체 정답 | 52 | 58 |
| 채점 대상 정답 | 52 | 54 |
| 채점 대상 채널 | tool_output 52 | tool_output 52 + prompt 2 |
| 비채점 tool_input 정답 | 0 | 4 |

**새 모델 실행의 개선 결과가 아니다.** n14 과제 재설계 후 실제 에이전트 재실행은 하지 않았다. n24 숫자는 동일한 원본 기록의 오프라인 라벨 수정 결과다. privesc 공개 원본은 없으므로 그 원본 재변환은 여전히 검증하지 못했다. 레거시 `path_tokens` 함수는 변경하지 않았다.

이 독립 검증은 이후 첫 4개 초안·약한 값 지원 코드가 추가되기 전의 상태에 대한 것이다. 최신 전체 미커밋 작업 트리의 통합 검증은 완료하지 않았다.

## 9. 취소 시 남은 첫 4개 초안과 기반 지원

| 후보 | 생성된 폴더 | 현재 상태 |
| --- | --- | --- |
| n01 | `metric-task/tasks_scenarios/n01-webhook-retry/` | 생성 초안, 독립 검증 전 |
| n02 | `metric-task/tasks_scenarios/n02-repo-test/` | 생성 초안, none_only 표시, 독립 검증 전 |
| n04 | `metric-task/tasks_scenarios/n04-deploy-snapshot/` | 생성 초안, 독립 검증 전 |
| n05 | `metric-task/tasks_scenarios/n05-tls-loader/` | 생성 초안, 독립 검증 전 |

새 생성기는 `metric-task/scripts/m2_trajectory_expansion.py`, 새 테스트는 `metric-task/scripts/test_m2_trajectory_expansion.py`다. 생성기의 `tasks()`는 위 네 개만 반환하고, `meta.generator=m2_trajectory_expansion`인 과제만 소유하는 구조임을 명령 허용 전에 확인했다. 생성 명령은 로그 캡처 방식으로 한 번 허용했다.

약한 값 지원을 위해 `m2_secrets.py`, `m2_tasks.py`, `m2_declarations.py`, `m2.py`, 관련 테스트·문서·축 파일에 변경이 남아 있다. 의도는 literal 고정값, none-only 사전 거부, 명시한 약한 값에만 제한적으로 허용하는 lint 예외다. **의도와 코드 존재를 확인한 것일 뿐, 기능 완성·회귀 안전성을 검증한 상태가 아니다.**

취소 직전 워커는 `/tmp/run_stage1_verify.py` 실행 확인 화면에서 대기하고 있었다. 사용자의 취소 이후 그 실행을 허용하지 않았다. 1차 검증 보고서 `/tmp/REPORT_trajectory_expansion_stage1.md`와 25개 전체 보고서는 작성되지 않았다. 따라서 새 네 과제의 자체 검사, 숨긴 변이 검사, 선언 감사, 약한 값 none-only 사전 거부, 기존 과제 fingerprint 보존, 전체 회귀 테스트를 완료했다고 주장하지 않는다.

나머지 미구현 후보는 **n06·n07·n08·n09·n10·n11·n12·n13·n15·n16·n17·n18·n20·n21·n22·n23·n25·n27·n28·n29·n30**, 총 21개다. 코드가 생긴 n01·n02·n04·n05도 미완료이므로 나머지 25개 구현 목표는 달성되지 않았다.

파일럿 5개와 생성 초안 4개를 합해 후보 폴더는 현재 9개다. 이것을 완료·검증된 후보 9개로 세면 안 된다. 새 초안의 실제 Claude 평가 실행은 한 번도 하지 않았다.

## 10. 하위 에이전트와 취소·종료 증거

Orca Run: `run_f6a6391517ea`.

| 실행 | 작업 | 최종 상태 |
| --- | --- | --- |
| `ctx_7362472d3641` / `task_6d75afc9cec0` | n14·n24 분석·수정 | worker_done succeeded, liveness exited, terminal released |
| `ctx_363462862c7c` / `task_99a54f7416db` | 나머지 25개 → 첫 4개로 축소 | 사용자 취소, state failed, liveness exited |

- 첫 실행 터미널: `term_8d50d9c0-8f63-4bfd-9dde-aed343143b67` — 이미 종료·해제 상태였다.
- 후속 터미널: `term_9612a584f4be848d8203ecf7063ed47f`.
- 후속 실행에 대한 `worker-stop`은 기존 `Keep open` 설정 때문에 `terminal_kept_open`으로 거부됐다. 종료됐다고 간주하지 않았다.
- 사용자의 명시적 전체 종료 지시에 따라 정확한 터미널의 작업·소유 정보를 확인하고 해당 탭만 직접 닫았다. `terminal close`는 **`ptyKilled=true`**를 반환했다.
- 이어서 `worker-show`는 **`stage=process_exited`, `liveness=exited`**, 종료 사유 `Terminal closed by operator request`를 반환했다. `worker-list`에서도 두 실행 모두 exited였다.
- 후속 Task를 `failed` 및 `cancelled by user`로 기록했다. `terminalState=retained`는 해당 실행의 이력·자원 회계 상태이며, 실제 실행 프로세스는 exited로 확인했다.
- 기본 collaboration 목록에도 root 외 하위 에이전트가 없었다. 다른 사용자 작업의 에이전트나 탭은 닫지 않았다.

과정 중 Orca/파일 접근 확인을 여러 차례 처리했다. 영구 권한 설정을 변경하지 않았으며, 일부 대화에 한정한 Orca 명령 허용만 선택했다. 값 일부를 출력하려는 점검 명령과 원시 테스트 출력을 직접 내보내는 명령은 취소하고, 안전한 요약·로그 캡처 방식으로 수정 요청했다.

## 11. 보존된 증거와 자료

### 원본과 영구 저장소 자료

- 인계 문서: `/Users/jungwoo/.local/share/promptguard-trajectory/HANDOFF.md` — 과거 진행 상태가 포함돼 있으므로 현재 상태는 이 파일을 우선한다.
- 후보 설계: `metric-detection/docs/README_trajectory-new-tasks.md`.
- 평가 설계·측정: `metric-detection/docs/README_trajectory-eval.md`.
- 판정 정책: `metric-detection/LABELING.md`.
- 원본 배치: `/Users/jungwoo/jw/CAU/26-2/CapstoneDesign/promptguard-data/runs/metric-task/trajectory_pilot_none_r1/`.
- 원본 배치 로그: 위 배치 경로 뒤에 `.log`를 붙인 파일. `.supervisor.json`도 같은 상위 경로에 있다.
- 초기 변환 세션·정답·labels: 동결 실행 워크트리의 `metric-detection/data_test`, `data_answer`, `labels_from_trajectory-trajectory_pilot_none_r1.jsonl`. 모두 git 제외 대상이다.
- 분석용 사본: 작업 워크트리의 `runs/trajectory-review-inputs/`. 원본이 아니라 읽기 편의를 위해 복사한 git 제외 자료다.

### 임시 증거 — /tmp는 영구 보관 장소가 아님

| 자료 | 경로 |
| --- | --- |
| 최초 파일럿 커버리지 | `/tmp/pilot_coverage.json` |
| 과제별 결과·기준선 결합 집계 | `/tmp/trajectory-pilot-analysis.json` |
| 파일럿 전 사용률 | `/tmp/trajectory-usage-before.json` |
| 파일럿 후 사용률 | `/tmp/trajectory-usage-latest.json` |
| agy n14·n24 보고서 | `/tmp/REPORT_n14_n24_and_25_candidates.md` |
| agy 재변환 | `/tmp/pilot_reconverted/` |
| Codex 원본 규칙 대조 결과 | `/tmp/codex-trajectory-independent-comparison.json` |
| Codex 독립 재변환 | `/tmp/codex-pilot-reconverted/` |
| Codex 독립 커버리지 | `/tmp/codex-pilot-reconverted-coverage.json` |
| Codex 독립 재현 검증 로그 | `/tmp/codex-pilot-reconverted-verify.log` |
| Codex 5개 검사 묶음 로그 | `/tmp/codex-agy-independent-0.log`부터 `-4.log` |
| 좁힌 sed 예외 검사 로그 | `/tmp/codex-refined-test_label_rules.py.log`, `/tmp/codex-refined-test_convert_trajectory.py.log` |
| 취소 시 변경 목록 | `/tmp/trajectory-cancelled-file-inventory.json` |
| 이전 n14·n24 패치 스냅샷 | `/tmp/trajectory-agy-review-combined.patch` — 이후 첫 4개 변경을 담은 전체 백업은 아님 |
| 실행되지 않은 1차 검증 스크립트 | `/tmp/run_stage1_verify.py` |

원본 로그·세션·planted·패치 내부의 값을 이 파일에 옮기거나 출력하지 않았다. 원본 실행 기록, 이전 백업, 기존 워크트리는 삭제하지 않았다.

## 12. 미결정·미검증 사항 — 재개 지시가 있을 때 참고만 할 것

이 목록은 자동 실행 지시가 아니다. 현재 작업은 취소됐다.

- 첫 4개 초안과 약한 값 기반 지원의 독립 코드 검토·기능·회귀 검증이 남았다. 현재 문서의 구현 안내가 먼저 갱신됐더라도 완료 증거로 믿으면 안 된다.
- 새 literal 값 생성·fingerprint 보존, 지정한 약한 값에만 예외를 주는지, run/play의 none 이외 조건이 모델 호출 전에 거부되는지 확인하지 못했다.
- n14 재설계 후 실제 세션의 도달률·길이 분포는 미측정이다.
- 나머지 21개는 미구현이며, 전체 25개를 완성했다는 결과가 없다.
- 출력 중앙값과 6,000자 초과 비율이 목표보다 높다는 파일럿 관찰은 남아 있다. 파일 크기 설계만으로 실제 세션 분포를 보장할 수 없다.
- 문맥별 표본 확인과 기존 사람 검토 19건이 남았다.
- 튜닝용/최종 평가용 분리는 미결정이다. 현재 기록을 보고 고친 규칙으로 최종 평가 점수를 내면 낙관 편향이 생길 수 있다.
- 키 파일 문맥에 서비스 계정 JSON을 포함할지, 기존 부족을 받아들일지는 미결정이며 문맥 정의는 바꾸지 않았다.
- 추적 쿠키와 ARN은 현 규칙에서 의도한 음성으로 잘 잡히지 않는다. 규칙을 임의로 넓히지 않았다.
- privesc 원본 부재, 구버전 recheck 미검증 등 기존 인계의 한계도 해소하지 않았다.
- 추가 유료 배치, main 변경, PR, 현재 미커밋 변경의 커밋·푸시는 수행하지 않았다.

## 13. 취소 시점의 미커밋 파일 목록

아래 목록은 에이전트 종료 후 수집한 스냅샷이다. **이 파일 자체를 제외하고 추적 파일 수정 21개, 새 파일 81개가 남았다.** 생성된 과제 파일은 템플릿이며 실행 시 비밀을 채우는 원본 기록과 구별된다. 파일 존재는 검증 완료를 뜻하지 않는다.

<!-- inventory is appended below -->

### 추적 파일 수정 21개

- `metric-detection/docs/README_trajectory-eval.md`
- `metric-detection/docs/README_trajectory-new-tasks.md`
- `metric-detection/scripts/label_rules.py`
- `metric-detection/scripts/test_convert_trajectory.py`
- `metric-detection/scripts/test_label_rules.py`
- `metric-task/README.md`
- `metric-task/scripts/m2.py`
- `metric-task/scripts/m2_declarations.py`
- `metric-task/scripts/m2_secrets.py`
- `metric-task/scripts/m2_tasks.py`
- `metric-task/scripts/m2_trajectory.py`
- `metric-task/scripts/test_m2_declarations.py`
- `metric-task/scripts/test_m2_trajectory.py`
- `metric-task/task_axes.toml`
- `metric-task/tasks_scenarios/n14-refund-review/task.json`
- `metric-task/tasks_scenarios/n14-refund-review/workspace/refunds/amounts.py`
- `metric-task/tasks_scenarios/n14-refund-review/workspace/refunds/disputes.py`
- `metric-task/tasks_scenarios/n14-refund-review/workspace/refunds/inventory.py`
- `metric-task/tasks_scenarios/n14-refund-review/workspace/refunds/payouts.py`
- `metric-task/tasks_scenarios/n14-refund-review/workspace/refunds/retries.py`
- `metric-task/tasks_scenarios/n14-refund-review/workspace/refunds/settlements.py`

### 새 파일 81개

- `metric-task/scripts/m2_trajectory_expansion.py`
- `metric-task/scripts/test_m2_trajectory_expansion.py`
- `metric-task/tasks_scenarios/n01-webhook-retry/check.py`
- `metric-task/tasks_scenarios/n01-webhook-retry/task.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/README.md`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/balances/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/credits/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/customers/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/disputes/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/invoices/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/orders/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/payouts/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/refunds/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/settlements/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/shipments/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/contracts/subscriptions/schema.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/payments/__init__.py`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/payments/settings.py`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/payments/webhook.py`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/tests/__init__.py`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/tests/fixtures/events.json`
- `metric-task/tasks_scenarios/n01-webhook-retry/workspace/tests/test_webhook.py`
- `metric-task/tasks_scenarios/n02-repo-test/check.py`
- `metric-task/tasks_scenarios/n02-repo-test/task.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/README.md`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/config/app.yaml`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/config/test.yaml`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/balances/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/customers/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/disputes/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/invoices/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/orders/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/refunds/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/contracts/shipments/schema.json`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/db/__init__.py`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/db/connection.py`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/db/repository.py`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/tests/__init__.py`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/tests/seed.sql`
- `metric-task/tasks_scenarios/n02-repo-test/workspace/tests/test_repository.py`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/check.py`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/task.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/CLAUDE.md`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/cli.py`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/balances/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/credits/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/customers/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/disputes/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/invoices/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/orders/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/payouts/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/refunds/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/settlements/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/shipments/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/contracts/subscriptions/schema.json`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/manifests/regions.ini`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/tests/__init__.py`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/tests/fixtures/credentials`
- `metric-task/tasks_scenarios/n04-deploy-snapshot/workspace/tests/test_cli.py`
- `metric-task/tasks_scenarios/n05-tls-loader/check.py`
- `metric-task/tasks_scenarios/n05-tls-loader/task.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/balances/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/customers/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/disputes/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/invoices/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/orders/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/refunds/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/contracts/shipments/schema.json`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/docs/tls.md`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/__init__.py`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/authorized_peers.conf`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_01.key`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_02.key`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_03.key`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_04.key`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_05.key`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_06.pem`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_07.pem`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/fixtures/keys/case_08.pem`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tests/test_tlsconfig.py`
- `metric-task/tasks_scenarios/n05-tls-loader/workspace/tlsconfig.py`

현재 이 문서만 추가 작성했으며, 위 파일을 수정·삭제하거나 git에 스테이징하지 않았다.

## 14. 취소 이후의 보존·정리 승인

사용자가 남은 수정·초안과 작업 내역을 커밋·푸시하고 워크트리를 정리하도록 추가 승인했다. 보존 대상은 n14·n24 검증·보완, 미검증 약한 값 기반 지원과 첫 네 과제 초안, 관련 테스트·문서, 이 파일이다. 실제 실행 데이터와 git 제외 분석 자료는 커밋 대상이 아니다. 워크트리 삭제 전에 전체 내용을 `.git` 제외 압축으로 별도 보관하고 이 문서 사본도 밖에 남긴다. 원격 브랜치와 커밋, 별도 동결 실행 워크트리, main 체크아웃, 원본 배치와 다른 워크트리는 유지한다. 추가 모델 실행·새 구현·검증 재개·main 병합·PR 생성은 이 승인에 포함되지 않는다.

### 보존 커밋 전 검사 메모

전체 보존 대상 103개 파일을 gitleaks로 검사했을 때 `m2_secrets.py`의 `openssh_key` 생성 함수 168~169행에서 private-key 탐지 1건이 있었다. 같은 행이 기존 HEAD와 바이트 단위로 같고 기존 HEAD만 따로 검사해도 동일 탐지가 발생함을 확인했다. AST 검토에서 반환값은 함수 호출 결과를 연결하는 문자열이며 상수 부분에는 PEM 머리글·꼬리글과 공백만 있고 개인키 본문은 없었다. 기존 생성 코드의 오탐으로 확인했으며 실제 값이 든 실행 데이터는 커밋하지 않는다. 나머지 102개 파일에서는 탐지가 없었다. 구현·테스트의 추가 실행은 하지 않았고 미검증 초안 상태를 유지했다.
