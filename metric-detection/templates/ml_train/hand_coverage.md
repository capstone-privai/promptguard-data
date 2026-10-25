# 손 템플릿 경계·퍼뜨림 커버리지

템플릿 160개, 세션 800개, item 3085개, 정답 4380 span, 음성 1450곳, mask 15곳.

split은 group 128/16/16, 세션 640/80/80 (train/val/test)이다.

규칙은 실제 빌드된 정답 span과 labels로 집계한다. 경계는 span 수, 퍼뜨림은 세션 수다. 한 span·세션이 여러 규칙에 집계될 수 있다. 음성 열은 해당 규칙을 충족한 세션 안의 모든 음성 위치 수이며 mask는 뺀다. 따라서 행 사이에서 중복되며, 규칙별 최소 음성 목표는 없다.

| 규칙 | 단위 | 3.4절 최소 | 실제 | 해당 세션의 음성 위치 | 충족 |
| --- | --- | ---: | ---: | ---: | :---: |
| 따옴표 안쪽 | span | 300 | 1635 | 1370 | ✓ |
| 뒤따르는 문장 부호 | span | 300 | 800 | 1150 | ✓ |
| 값 자체가 문장 부호로 끝남 | span | 300 | 400 | 400 | ✓ |
| Bearer 스킴 | span | 200 | 200 | 400 | ✓ |
| Basic 스킴 (base64 전체) | span | 200 | 200 | 400 | ✓ |
| token 스킴 | span | 200 | 200 | 400 | ✓ |
| URL 속 비밀번호·토큰 (스킴 ≥ 6종) | span | 400 | 400 | 800 | ✓ |
| user:password | span | 200 | 200 | 400 | ✓ |
| 연결 문자열 Password=…; | span | 200 | 200 | 400 | ✓ |
| 인증 쿠키와 속성 | span | 200 | 200 | 400 | ✓ |
| PEM 전체 | span | 150 | 150 | 150 | ✓ |
| 잘린 PEM (본문 포함) | span | 150 | 150 | 150 | ✓ |
| JSON 이스케이프 PEM | span | 150 | 150 | 150 | ✓ |
| 줄바꿈으로 끊긴 값 | span | 150 | 150 | 300 | ✓ |
| base64 인코딩 | span | 150 | 150 | 300 | ✓ |
| URL 인코딩 | span | 150 | 251 | 502 | ✓ |
| JSON 인코딩 | span | 150 | 300 | 450 | ✓ |
| 맞닿은 값 병합 | span | 100 | 100 | 200 | ✓ |
| 흔한 값: 자격증명·일반 자리 | session | 400 | 400 | 800 | ✓ |
| 고유값: 로그 재등장 | session | 600 | 600 | 1150 | ✓ |
| 고유값: 식별자 재등장 (음성) | session | 150 | 150 | 300 | ✓ |

URL 스킴: amqp, amqps, bolt, bolt+s, clickhouse, clickhouses, ftp, ftps, http, https, imaps, kafka, ldaps, memcached, mongodb, mongodb+srv, mqtt, mqtts, mssql, mysql, pop3s, postgres, postgresql, redis, rediss, rsync, sftp, smtp, smtps, sqlserver.

| 음성 kind | 위치 수 |
| --- | ---: |
| `auth_setting` | 75 |
| `doc_example` | 25 |
| `empty` | 5 |
| `hash` | 60 |
| `identifier` | 480 |
| `non_credential` | 20 |
| `not_propagated` | 110 |
| `pem_header` | 55 |
| `prefix_example` | 55 |
| `prefix_redaction` | 55 |
| `prefix_template` | 50 |
| `public_key` | 50 |
| `public_key_raw` | 130 |
| `redaction` | 30 |
| `reference` | 25 |
| `secret_ref` | 65 |
| `template` | 40 |
| `template_ko` | 80 |
| `wallet_address` | 40 |

중복 검사: 값·숫자를 가린 item의 5-token shingle 집합을 전수 비교한다 (정확한 Jaccard, 기준 0.8). split 사이 유사 item 쌍 0개.

검사 결과: 통과.
