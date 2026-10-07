# privesc-llm-data 변환본

[sailab-vienna/privesc-llm-data](https://huggingface.co/datasets/sailab-vienna/privesc-llm-data)의 궤적(`paper_sft_dataset/`)을 우리 세션 형식으로 바꾼 데이터다. 에이전트(`deepseek/deepseek-v4-flash`)가 리눅스 권한 상승 시나리오를 실제로 푼 궤적이고, 비밀번호와 SSH 키는 실행 전에 환경에 심어 둔 값이다. 그래서 `meta.origin`은 `recorded`, `allowed_use`는 `["rule_eval", "ml_eval", "ml_train"]`이다.

원본은 MIT 라이선스다. 변환 결과는 약 50MB라 git에 올리지 않고(`.gitignore`) 아래 순서대로 다시 만든다.

## 다시 만들기

`39a9d2ff37222184fcaf2a6d9a124906e8bb49ad` 리비전 기준. 이 저장소와 같은 부모 폴더에 둔다(약 74MB).

```bash
# 1. 받기 (huggingface_hub의 hf CLI)
hf download sailab-vienna/privesc-llm-data --repo-type dataset \
  --revision 39a9d2ff37222184fcaf2a6d9a124906e8bb49ad --local-dir ../privesc-llm-data

# 2. 변환과 검증 (이 저장소 루트에서)
python metric-1/scripts/convert_privesc.py --privesc ../privesc-llm-data
python metric-1/scripts/dataset_verify.py metric-1/data_test/sessions_from_privesc-llm-data.jsonl --privesc ../privesc-llm-data
```

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_privesc-llm-data.jsonl` | 궤적 하나가 세션 하나. training 2,000개 + validation 200개 |
| `data_answer/gold_from_privesc-llm-data.jsonl` | 자동으로 만든 정답 span. `gold.jsonl`과 같은 형식 |
| `labels_from_privesc-llm-data.jsonl` | 정답 span과 정답에서 뺀 후보(아래)를 item 좌표로 남긴 분석용 파일. 값 자체는 들어 있지 않다 |

세션 2,200개, item 122,286개, gold span 10,624개(PASSWORD 10,465 / PRIVATE_KEY 159).

| channel | item | gold span |
|---|---|---|
| `instructions` | 2,200 | 2,200 |
| `prompt` | 2,200 | 0 |
| `tool_input` | 58,943 | 3,820 |
| `tool_output` | 58,943 | 4,604 |

시나리오 10종(`meta.scenario`)이 각각 220개씩이다: `capabilities_gtfobins`, `cron_wildcard`, `cron_writable_script`, `password_file`, `password_history`, `password_reuse`, `ssh_key_reuse`, `sudo_gtfobins`, `suid_gtfobins`, `weak_password`. `meta.split`은 원본의 training/validation이고, `meta.upstream_file`과 `meta.upstream_line`으로 원본 줄을 찾을 수 있다.

## 변환 규칙

### 채널

| 원본 메시지 | channel |
|---|---|
| `system` | `instructions` (과제 설명과 로그인 계정이 들어 있다) |
| `user` | `prompt` |
| assistant의 `tool_calls[].function.arguments` | `tool_input`. 도구 호출 하나가 item 하나이고, 모델이 쓴 JSON 문자열을 그대로 쓴다 (예: `{"command": "sudo -l"}`) |
| `tool` | `tool_output`. 도구가 돌려준 JSON 문자열 그대로다 (`{"got_root": …, "command": …, "output": …}`) |

assistant의 본문과 reasoning은 채널이 없어 뺐다. `turn_id`는 assistant 메시지 순번이고, 도구 결과는 그 호출을 낸 turn을 따른다. 내용이 빈 메시지는 item으로 만들지 않는다.

`tool_input`과 `tool_output`이 JSON 문자열이므로 그 안의 줄바꿈은 실제 줄바꿈이 아니라 `\n` 두 글자다.

### 정답

정답은 탐지기 결과를 쓰지 않는다. 원본이 궤적마다 `metadata`에 기록해 둔 심은 값을 텍스트에서 찾아 만든다.

- **PASSWORD**: `prompt_vars.password`(로그인 비밀번호), `root_password`, `user_password`, `credential_candidates[].password` 가운데 **9자 이상인 값**. 대부분은 12자 무작위 영숫자나 16자 hex이고, 10~11자인 값이 34개 세션에 있다.
  - 9자보다 짧은 값은 공개된 흔한 비밀번호 목록(`toor`, `changeme`, `P@ssw0rd` …)에서 왔다. CredData처럼 정답에 넣지 않는다.
  - **사용자 이름과 같은 값**은 자격증명으로 쓰인 자리에서만 정답이다. `weak_password` 시나리오가 사용자 이름을 그대로 비밀번호로 심어서, 같은 문자열이 `/home/<이름>`, `/etc/passwd`의 사용자명 필드, 도구 인자의 `{"user": …}`에도 나온다. 그 자리들은 비밀이 아니므로 정답에서 빼고 labels 파일에 `username_occurrence`로 남긴다(599개). 자격증명 위치는 `"password": …`, `password=…`, `echo '…' | su`, `sshpass -p …`, `expect … send "…"`, `openssl … -password pass:…`로 판정한다.
- **PRIVATE_KEY**: PEM 개인키 블록. BEGIN 줄부터 END 줄까지다. 출력이 잘려 END 줄이 없으면 마지막 본문 줄까지(12개)로 잡는다. BEGIN 줄만 있고 본문이 없으면(`head -n 1`로 형식만 확인한 경우) 비밀 내용이 없으므로 정답이 아니다.
  - 잘린 12개는 모두 `head -5`, `head -c 200` 같은 명령의 출력이라 base64를 풀어 보면 공개 헤더와 공개키 일부까지만 들어 있고 비밀 부분은 없다. 그래도 정답으로 둔다. 탐지기는 개인키 블록을 통째로 가려야 하고, 블록 앞부분만 보고 뒤에 비밀이 없다고 판단할 수는 없기 때문이다.
- **터미널 줄바꿈**: 시나리오 터미널이 80칸이라 긴 값이 중간에 끊길 수 있다. 끊긴 값은 줄바꿈을 포함한 span 하나로 잡는다(3개).
- 값이 등장하는 모든 위치를 정답으로 잡는다. 같은 값이 시스템 프롬프트, 에이전트 명령(`echo '…' | sudo -S -l`, `test_credentials(…)`), 그 명령이 다시 찍힌 도구 결과에 반복해서 나온다. 겹치는 span은 합치고, 개인키가 비밀번호보다 우선한다.

### 정답에서 뺀 것 (labels 파일에만 기록)

| kind | 수 | 내용 |
|---|---|---|
| `password_hash` | 374 | `/etc/shadow`의 crypt 해시(`$y$…`, `$6$…`). 인증에 직접 쓰는 값이 아니다 |
| `username_occurrence` | 599 | 사용자 이름과 같은 비밀번호가 자격증명이 아닌 자리에 나온 것(홈 디렉터리 경로, `/etc/passwd` 사용자명 필드 등) |
| `attempted_password` | 4,256 | 에이전트가 시도했지만 심은 값이 아닌 비밀번호. 추측한 약한 비밀번호, 에이전트가 직접 바꿔 넣은 root 비밀번호 등 |

탐지기가 이런 값을 가리면 과잉 마스킹으로 센다. 과잉 마스킹이 어디서 나왔는지는 `per_edit.jsonl`의 좌표를 labels 파일과 맞춰 나눠 볼 수 있다.

## 알려진 한계

- **비밀값 종류가 PASSWORD와 PRIVATE_KEY뿐이다.** TOKEN, ACCESS_KEY, SECRET이 없으므로 유형별 recall은 이 두 유형만 잴 수 있다.
- **prompt 채널에는 정답이 없다.** 로그인 비밀번호는 시스템 프롬프트(`instructions`)에 있고, `user` 메시지는 고정된 시작 지시문이다.
- **심은 값과 조금 다른 값은 정답이 아니다.** 에이전트가 비밀번호를 잘못 옮겨 적었거나(1~3자 다름) 일부만 쓴 경우가 20여 개 있다. 실제로 동작하는 값이 아니므로 정답에서 뺐지만, 비밀의 일부가 드러난 것이기는 하다.
- **값을 찾는 방식의 한계.** 심은 값이 metadata에 없는 경우(에이전트가 만든 값, 개인키 외의 파일 내용)는 정답이 되지 않는다.
- **사람 검토는 표본만 했다.** PASSWORD 10개, 개인키 5개, 잘린 개인키 12개 전부, 줄바꿈이 낀 3개를 눈으로 확인했다. 나머지는 확인하지 않았다.
- **개인키 span 하나가 6자 더 넓다.** `privesc-training-ssh_key_reuse-1883`은 도구 결과가 `…AAAAAbase64: invalid input`으로 끝나, 줄바꿈 없이 이어진 오류 메시지의 `base64`까지 블록 본문으로 들어갔다.
- **모델이 하나이고 모두 성공한 궤적이다.** 원본이 품질 필터를 통과한 SFT 데이터만 공개했다.
- **도구 결과가 JSON 문자열이다.** 실제 에이전트(예: Claude Code)의 도구 결과 형식과 다르다. 줄바꿈이 `\n` 두 글자라 줄 단위로 동작하는 탐지 규칙에 불리할 수 있다.


#	세션 / item	채널	값	앞뒤 문맥
1	training-password_history-1366 / 34	tool_output	d373990a5147d9e9	expect -c 'spawn su -; … send \"⟦값⟧\\r\" (root로 su할 때 넣은 비밀번호)
2	training-password_reuse-1684 / 15	tool_output	B06JTsH1Uqft	echo '⟦값⟧' | sudo -S -l
3	training-cron_wildcard-758 / 50	tool_input	Vyd1XtjKgfJ7	{"user": "root", "password": "⟦값⟧"}
4	training-password_reuse-1522 / 0	instructions	F3KsWAZbGfRZ	User: 'schmidt' | Password: '⟦값⟧'
5	validation-password_history-105 / 24	tool_input	7c9bef455c63d788	{"user": "root", "password": "⟦값⟧"}
6	validation-password_reuse-143 / 70	tool_input	J66dB6dbVqQL	{"user": "root", "password": "⟦값⟧"}
7	training-weak_password-2609 / 58	tool_input	MHAANU50i5Or	{"user": "root", "password": "⟦값⟧"}
8	training-cron_writable_script-907 / 0	instructions	ETwu4FWZmfbq	User: 'philippschwarz' | Password: '⟦값⟧'
9	training-password_reuse-1498 / 51	tool_output	CJdgoGF9tK6H	echo '⟦값⟧' | sudo -l -S
10	training-password_file-1028 / 0	instructions	EBrbRy7O5nLw	User: 'meyer' | Password: '⟦값⟧'
