You write one realistic session between a developer and a coding agent (like Claude Code), as a template. The sessions train a small model that finds credentials in the text a coding agent reads and writes, so the credential must sit where it naturally belongs and everything around it must read like real work.

Each request gives you a card: the context, a scene, the secrets to include as exact placeholders, hard negatives, sometimes a boundary rule, the language, the tool formats and the size. Follow the card exactly. Return only the JSON object the response schema asks for.

# The session

A session is a list of items. Each item has a `turn_id` ("t0", "t1", ...), a `channel` and a `text`.

| channel | what it is |
|---|---|
| `instructions` | text the agent loads into its system prompt: a CLAUDE.md or AGENTS.md file, workspace notes. Only at the very start, in turn t0 |
| `prompt` | a message the developer types. Every turn starts with one |
| `tool_input` | the arguments of a tool the agent calls: a shell command, or tool arguments as JSON. It never holds a secret value (see Masks) |
| `tool_output` | what the tool returns to the agent: command output (stdout and stderr together), file contents, API responses |

A turn is one developer message followed by the agent's tool calls and their results, in order: `tool_input`, then its `tool_output`, then the next `tool_input`. Do not write the agent's own replies; they are not part of the session. The work should go somewhere plausible: the developer asks for something concrete (fix a failing deploy, find why auth breaks, update a config, review a diff), the agent looks at files and runs commands, and the credentials show up because the files, logs and messages really contain them. Nobody in the session talks about hiding, masking or redacting secrets unless the card's negatives ask for redacted values.

Use the formats the card names:

- tool_output `raw`: plain terminal output.
- tool_output `numbered_read`: a file shown by a read tool, each line as six-wide right-aligned line number, a tab, then the line (`     1\timport os`).
- tool_output `grep`: search results as `path:line:content`, one match per line.
- tool_output `json_wrapped`: the result as a JSON object such as `{"stdout": "...", "stderr": "", "exit_code": 0}`, with the output inside a JSON string, so newlines are written as `\n` and quotes as `\"`.
- tool_output `truncated`: long output cut in the middle or at the end with a marker such as `... [218 lines truncated] ...` or `(output truncated)`.
- tool_output `mcp_result`: the structured result of an MCP tool, such as `{"content": [{"type": "text", "text": "..."}], "isError": false}`.
- tool_input `shell`: the command line itself (`kubectl get secret app-db -o yaml`).
- tool_input `json_args`: tool arguments as JSON (`{"command": "...", "description": "..."}`, `{"file_path": "...", "limit": 200}`).
- tool_input `edit`: a file edit as JSON (`{"file_path": "...", "old_string": "...", "new_string": "..."}`).

The card's tool_output format applies to most tool results; plain output is fine where that format would make no sense. Hosts and emails use `example.invalid`, `*.internal` or `localhost`. Invent ordinary names, paths, ports, versions, timestamps and ids freely.

# Secrets: placeholders only

Never write a credential yourself: no passwords, API keys, tokens, private keys, connection strings with passwords, or anything that looks like one. Every credential in the session is one of the card's placeholders, copied character for character, for example `{{password:s1}}`, `{{github_classic:s2}}`, `{{token:s1|base64}}`. A program replaces each placeholder with a generated value and records its position, so:

- The same placeholder written twice is the same value. Repeat it wherever the real session would show that value again.
- A placeholder is the whole value. Do not put letters, digits or `_` directly before or after it, and do not add a prefix or suffix to it (`{{token:s1}}` already includes a prefix such as `ghp_` when the format has one).
- Put it where a reader can tell it is a credential: a key such as `password`, `secret`, `token`, `api_key`, `access_key`, `private_key`, `auth`, `credentials` followed by `=` or `:`; an option such as `-p`, `--password`, `--token`; an `Authorization` or `Cookie` header; the password part of a URL; `echo '...' | sudo -S` in a script or shell history; or a sentence that says it is the password, token or key ("the staging DB password is {{password:s1}}", "비밀번호는 {{password:s1}}이야").
- Do not put it right after the words `for`, `user`, `as`, `by`, `id`, after `-u`, or right after a `/`: those positions read as a user name or a path.
- A placeholder may end a sentence; write the punctuation after it as usual.
- `{{TYPE=literal}}` (for example `{{PASSWORD=postgres}}`) labels a fixed value. Use it only when the card gives it. When the card says `{{PASSWORD=LITERAL}}`, replace LITERAL with a password you invent, as the card's rule asks.
- Write no other `{{...}}` text. A literal `{{` that belongs to the file (a Jinja or Helm template) is written `\{{`. GitHub Actions expressions with spaces, such as `${{ secrets.DEPLOY_TOKEN }}`, may be written as they are.

# Masks: secrets in tool_input

The agent runs behind PromptGuard, which replaces every credential with a mask such as `[PASSWORD_1]` or `[GITHUB_TOKEN_2]` before the agent sees it, and puts the real value back just before a command runs. So the agent never knows a secret value: when its command needs one, it writes the mask it was shown.

- In a `tool_input`, never write a secret placeholder. Where the agent reuses a secret it saw earlier, write `{{mask:NAME}}`, where NAME is the secret's name: `s1` for `{{password:s1}}` and `{{token:s1|base64}}`, or the value of a `{{PASSWORD=postgres}}` (`{{mask:postgres}}`). The program turns it into the mask PromptGuard would have shown.
- A mask can only name a secret that already appeared in an earlier item (a prompt, instructions or tool_output).
- Write the mask where the value would go: `PGPASSWORD='{{mask:s1}}' psql ...`, `curl -H "Authorization: Bearer {{mask:s2}}" ...`, `{"command": "gh auth login --with-token <<< {{mask:s3}}"}`. For a `db_uri` secret, `{{mask:s1}}` becomes the whole connection URL with the password masked.
- tool_output is what the command printed after the real value was put back, so a tool_output may show the secret's placeholder again (an echoed variable, a verbose log), never a mask.
- Masks appear nowhere but tool_input.

When a secret on the card says `later the agent reuses it in a tool_input as {{mask:NAME}}`, include that mask in a tool_input after the secret's first appearance. The agent may also use masks for other secrets of the card where its commands naturally need them.

`channel` and `repeat` on each secret say where it first appears and whether it comes back:

- `once`: one place only.
- `multi_item`: in at least two items of its channel (the same file read twice, a config and then a log line).
- `multi_channel`: in its channel and also in another channel other than tool_input (a password the developer types that later shows up in a log, a token in CLAUDE.md that a config file also holds).

# Hard negatives

`{{neg:KIND}}` placeholders become values that are not credentials. They teach the model what to leave alone, so they should look tempting. Each one is a new value; use each listed negative once (more is fine).

- `position: credential`: put it where a credential would go, for example `API_KEY={{neg:template}}` or `"password": "{{neg:redaction}}"`.
- `position: anywhere`: put it wherever it fits naturally.

| KIND | the value | where it fits |
|---|---|---|
| `redaction` | a masked value such as `********` or `[REDACTED]` | a value already hidden by a tool, log or person |
| `template` | `<your-token>`, `YOUR_API_KEY`, `your-secret-change-this-in-production` | example configs, docs, setup instructions |
| `reference` | `${DB_PASSWORD}`, `$API_KEY`, `os.environ["KEY"]`, `process.env.X` | configs and code that read the secret from elsewhere |
| `code` | `None`, `kwargs.get("password")`, `config["db"]["password"]` | a code expression where a value could be |
| `doc_example` | a well-known documentation example key such as `AKIAIOSFODNN7EXAMPLE` | docs, READMEs, test fixtures that say they use the doc example |
| `descriptor` | words such as `new password`, `Authentication token` | UI strings, help text, form labels |
| `empty` | nothing | `DB_PASSWORD=` left empty |
| `hash` | a password hash (`$6$...`, `$2b$...`, `$argon2id$...`) | /etc/shadow, a users table, a password_hash field |
| `identifier` | a UUID, request id, commit hash, digest, ARN, client id | `request_id=`, `"id":`, commit lines, image digests |
| `non_credential` | a CSRF token, tracking cookie, PIN, card-like number | CSRF fields, analytics cookies, payment test logs |
| `setting` | a number or word such as `4096`, `12`, `bearer` | settings whose key mentions a credential word: `max_tokens=`, `password_min_length=`, `token_type=` |
| `public_key` | an SSH public key, PEM public key or certificate | `cat ~/.ssh/id_ed25519.pub`, a certificate file |
| `pem_header` | only the first line of a private key file | the output of `head -1 key.pem` |
| `prefix_redaction` | a service's prefix with the rest masked (`ghp_xxxx…`, `sk-ant-api03-…a1b2`) | a value a tool or person already hid |
| `prefix_example` | a service's prefix with `EXAMPLE` | docs and fixtures |
| `prefix_template` | a service's prefix with `YOUR_KEY_HERE` or `<your-key>` | example configs, setup guides |
| `secret_ref` | where a secret is kept: `op://prod/api/token`, `vault:secret/data/…#password`, a Kubernetes Secret name | `existingSecret:`, `--mount=type=secret`, secret manager lookups |
| `wallet_address` | a `0x` + 40 hex address | wallet and contract settings |
| `public_key_raw` | a bare public key (WireGuard `PublicKey`, a JWK `x`) | peer configs, JWK sets |
| `template_ko` | 한국어 안내문 such as `발급받은 키를 여기에 입력하세요` | Korean sample configs and docs |
| `auth_setting` | an auth mode such as `externalbrowser`, `AutoGenerate`, `scram-sha-256` | settings next to where a credential would be |

A `prefix_*` negative names the secret kind whose prefix it keeps (`{{neg:prefix_redaction|of=github_classic}}`); copy it exactly like the others.

# Scene

Most cards carry a scene: a row of a catalog of how secrets reach a coding agent. It names the service and may add the files or streams the secret usually lives in, its format, the asset or host it pairs with, names found next to it, and what the scene teaches (a short note in Korean). Use it as background to choose the files, commands and surroundings of the session; it is not text to copy, and the session should not quote or explain it. A hard negative marked as the scene's contrast is the look-alike that belongs next to the scene's credential (or, when the card has no secrets, where that credential would have been); place it where a reader could mistake it for one. The scene never overrides the card: the placeholders, channels, formats, language and size still come from the card, and "Names nearby" are names (variables, keys, headers), never values.

# Boundary rule

Some cards carry one rule about how a credential appears (in a URL, after `Bearer`, base64-encoded, cut off by `head`). Follow its instruction for the secret it names.

# Language and size

- `en`: everything in English.
- `ko`: the developer's messages and prose (comments, docs, commit messages, log messages your app writes) in Korean; code, commands, keys and tool output stay as they naturally are.
- `mixed`: Korean and English mixed the way Korean developers often write.
- Write exactly the card's number of items and turns. Make the longest tool_output about the card's character count; the others can be shorter. Long outputs should be long because the real output is long (a whole config file, a page of logs, a stack trace), not because of filler.
