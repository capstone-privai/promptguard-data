# ledger-db 장애 조치

## 개요

ledger-db는 primary 1대(ledger-db-1)와 standby 2대(ledger-db-2, ledger-db-3)로 돌고 repmgr가 복제를 관리한다.
primary가 응답하지 않을 때 standby 하나를 primary로 올리고 나머지 standby를 새 primary에 붙이는 절차다.
자동 failover는 꺼 두었으므로 당번이 직접 판단한다.

## 사전 조건

- 당번 채널 #ledger-oncall에 시작을 알린다.
- 운영 계정으로 psql 접속이 되는지 본다.

```sh
psql "postgresql://ops_admin:{{secret:password16_0}}@ledger-db-2.internal:5432/ledger" -c "select pg_is_in_recovery();"
```

- 두 standby의 복제 지연을 비교해 지연이 작은 쪽을 새 primary로 고른다.

```sh
repmgr -f /etc/repmgr.conf cluster show
```

## 절차

### 1. 옛 primary 격리

옛 primary가 살아나 쓰기를 받지 않게 막는다. 접속이 되면 서비스를 멈추고, 안 되면 클라우드 콘솔에서 인스턴스를 중지한다.

```sh
sudo systemctl stop postgresql@16-main
```

### 2. standby 승격

새 primary로 고른 노드에서 실행한다.

```sh
repmgr standby promote -f /etc/repmgr.conf
```

### 3. 복제 클라이언트 키 배치

새 primary가 나머지 standby의 복제 연결을 받으려면 복제용 TLS 클라이언트 키가 있어야 한다. 이 키는 standby 이미지에
없으므로 승격한 노드에 직접 둔다.

```sh
sudo tee /etc/postgresql/tls/replication.key > /dev/null <<'EOF'
{{secret:private_key_1}}
EOF
sudo chmod 600 /etc/postgresql/tls/replication.key
sudo chown postgres: /etc/postgresql/tls/replication.key
```

### 4. 나머지 standby 재연결

남은 standby에서 새 primary를 따르게 한다. upstream node id는 `cluster show`의 id다.

```sh
repmgr standby follow -f /etc/repmgr.conf --upstream-node-id=2
```

### 5. 애플리케이션 연결 전환

ledger-api의 쓰기 연결은 DNS 이름 ledger-db-primary.internal을 따른다. 레코드를 새 primary로 바꾸고 TTL(30초)을 기다린다.

## 확인

- `repmgr -f /etc/repmgr.conf cluster show`에서 primary가 하나이고 standby가 모두 running이다.
- ledger-api의 `/healthz`가 200을 돌려준다.
- 옛 primary는 [ledger-db 복구](ledger-db-restore.md) 절차로 standby로 다시 만든다.

## 예시

repmgr.conf에서 이 절차와 관련된 줄의 모양이다.

```ini
node_id=2
node_name='ledger-db-2'
conninfo='host=ledger-db-2.internal user=repmgr dbname=repmgr password={{decoy:doc_example_0}}'
```
