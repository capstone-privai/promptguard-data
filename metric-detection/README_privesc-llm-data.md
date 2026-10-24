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
python metric-detection/scripts/convert_privesc.py --privesc ../privesc-llm-data
python metric-detection/scripts/dataset_verify.py metric-detection/data_test/sessions_from_privesc-llm-data.jsonl --privesc ../privesc-llm-data
```

## 결과

| 파일 | 내용 |
|---|---|
| `data_test/sessions_from_privesc-llm-data.jsonl` | 궤적 하나가 세션 하나. training 2,000개 + validation 200개 |
| `data_answer/gold_from_privesc-llm-data.jsonl` | 자동으로 만든 정답 span. `gold.jsonl`과 같은 형식 |
| `labels_from_privesc-llm-data.jsonl` | 정답 span과 정답에서 뺀 후보(아래)를 item 좌표로 남긴 분석용 파일. 값 자체는 들어 있지 않다 |

세션 2,200개, item 122,286개, gold span 15,669개(PASSWORD 15,510 / PRIVATE_KEY 159).

| channel | item | gold span |
|---|---|---|
| `instructions` | 2,200 | 2,200 |
| `prompt` | 2,200 | 0 |
| `tool_input` | 58,943 | 6,309 |
| `tool_output` | 58,943 | 7,160 |

`tool_input`의 정답 6,309개는 데이터에 그대로 두지만 채점하지 않는다. 에이전트가 직접 쓴 명령이라 가릴 대상이 아니라, 실행 직전에 placeholder를 원래 값으로 되돌리는 자리이기 때문이다([채점 기준](README.md#단위)). 채점하는 정답은 `instructions`와 `tool_output`의 9,360개(PASSWORD 9,201 / PRIVATE_KEY 159)다.

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

정답은 탐지기 결과를 쓰지 않는다. [LABELING.md](LABELING.md)의 기준을 [scripts/label_rules.py](scripts/label_rules.py)로 적용한다.

- **PASSWORD 후보**: `metadata`에 심은 값(`prompt_vars.password`, `root_password`, `user_password`, `credential_candidates[].password`)과 에이전트가 시도한 비밀번호(`test_credentials(…)`, `echo '…' | su`, `sudo -S`, `sshpass -p …`)다. 길이는 보지 않는다. 심은 값인지, 실제로 동작하는지도 판정에 쓰지 않는다.
- 후보가 나온 **모든 위치**를 앞뒤 문맥으로 판정한다(`label_rules.classify`).
  - **자격증명 자리**(`"password": …`, `echo '…' | sudo -S`, `sshpass -p`, `chpasswd`, `mysql -p…`, `os.write(fd, b'…')`, "Set root password to …" 등)에 있으면 정답이다(labels의 `credential_slot`).
  - 그 밖의 위치는 **고유한 값**이면 정답이고(`propagated`), **흔한 값**이면 정답이 아니다(`not_propagated`). 흔한 값은 `label_rules.is_common`(SCOWL 영어 단어, SWE-Gym·openhands에 흔한 토큰, 숫자만)에 걸리거나, 그 궤적의 사용자명, 컨테이너 호스트 이름, 경로 일부와 같은 값이다. `weak_password` 시나리오가 사용자명을 그대로 비밀번호로 쓰는 경우가 여기에 든다.
  - **식별자 자리**(사용자명, 경로, 호스트 이름, `ls -l`·`ps` 소유자 칸, `/etc/passwd` 사용자명 필드)는 값이 고유해도 정답이 아니다(`identifier`).
- 규칙은 이 데이터의 후보 등장 80,289곳으로 다듬었고, 판정 유형별로 층을 나눈 표본 100곳을 사람이 검수해 모두 맞았다.
- **PRIVATE_KEY**: PEM 개인키 블록. BEGIN 줄부터 END 줄까지다. 출력이 잘려 END 줄이 없으면 마지막 본문 줄까지(12개)로 잡는다. BEGIN 줄만 있고 본문이 없으면(`head -n 1`로 형식만 확인한 경우) 비밀 내용이 없으므로 정답이 아니다.
  - 잘린 12개는 모두 `head -5`, `head -c 200` 같은 명령의 출력이라 base64를 풀어 보면 공개 헤더와 공개키 일부까지만 들어 있고 비밀 부분은 없다. 그래도 정답으로 둔다. 탐지기는 개인키 블록을 통째로 가려야 하고, 블록 앞부분만 보고 뒤에 비밀이 없다고 판단할 수는 없기 때문이다.
- **터미널 줄바꿈**: 시나리오 터미널이 80칸이라 긴 값이 중간에 끊길 수 있다. 끊긴 값은 줄바꿈을 포함한 span 하나로 잡는다(3개).
- 겹치는 span은 합치고, 개인키가 비밀번호보다 우선한다. 에이전트 명령(`tool_input`)의 정답은 만들어 두되 채점하지 않는다(위 채널 표 아래).

### 정답에서 뺀 것 (labels 파일에만 기록)

| kind | 수 | 내용 |
|---|---|---|
| `password_hash` | 374 | `/etc/shadow`의 crypt 해시(`$y$…`, `$6$…`). 인증에 직접 쓰는 값이 아니다 |
| `identifier` | 56,745 | 후보 값이 식별자 자리에 나온 것. 대부분 `ls -l` 소유자 칸의 `root` |
| `not_propagated` | 9,649 | 흔한 값이 자격증명 자리 밖에 나온 것. JSON 키 `"password"`, 시스템 프롬프트의 "root shell", 검색어, cron 사용자 칸 등 |

후보 등장 행에는 판정한 규칙(`rule`)과 값의 분류(`value_class`: `common`/`distinct`)가 같이 있다.

탐지기가 이런 값을 가리면 과잉 마스킹으로 센다. 과잉 마스킹이 어디서 나왔는지는 `per_edit.jsonl`의 좌표를 labels 파일과 맞춰 나눠 볼 수 있다.

## 알려진 한계

- **비밀값 종류가 PASSWORD와 PRIVATE_KEY뿐이다.** TOKEN, ACCESS_KEY, SECRET이 없으므로 유형별 recall은 이 두 유형만 잴 수 있다.
- **prompt 채널에는 정답이 없다.** 로그인 비밀번호는 시스템 프롬프트(`instructions`)에 있고, `user` 메시지는 고정된 시작 지시문이다.
- **심은 값과 조금 다른 값은 정답이 아니다.** 에이전트가 비밀번호를 잘못 옮겨 적었거나(1~3자 다름) 일부만 쓴 경우가 20여 개 있다. 실제로 동작하는 값이 아니므로 정답에서 뺐지만, 비밀의 일부가 드러난 것이기는 하다.
- **값을 찾는 방식의 한계.** 심은 값이 metadata에 없는 경우(에이전트가 만든 값, 개인키 외의 파일 내용)는 정답이 되지 않는다.
- **사람 검토는 표본만 했다.** PASSWORD 후보 등장 100곳(층화 표본, 오류 0), 개인키 5개, 잘린 개인키 12개 전부, 줄바꿈이 낀 3개를 눈으로 확인했다. 표본 오류가 0이어도 층마다 오류율 상한(95%)은 9~18%다.
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
