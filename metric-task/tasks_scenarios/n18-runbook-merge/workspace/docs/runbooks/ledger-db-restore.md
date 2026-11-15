# ledger-db 복구

## 개요

잘못된 배포나 운영 실수로 데이터가 손상됐을 때 특정 시각으로 되돌리는 절차다. 운영 DB를 바로 덮지 않고
복구 전용 인스턴스 ledger-db-restore에서 먼저 복구해 확인한 뒤 전환한다.

## 사전 조건

- 되돌릴 시각(UTC)을 당번과 서비스 담당이 함께 정한다.
- ledger-api를 점검 모드로 바꿔 쓰기를 막는다.

## 절차

### 1. 덤프 파일로 복구

가장 최근 덤프를 받아 복구 인스턴스에 풀어 넣는다.

```sh
aws s3 cp s3://ledger-backups/dumps/ledger-latest.dump /backups/ledger-latest.dump
PGPASSWORD='{{secret:password_dollar_0}}' pg_restore --clean --if-exists -h ledger-db-restore.internal -U restore_admin -d ledger /backups/ledger-latest.dump
```

### 2. 시점 복구

pgBackRest로 정한 시각까지 WAL을 재생한다. ledger-db-restore에서 실행한다.

```sh
sudo systemctl stop postgresql@16-main
sudo -u postgres pgbackrest --stanza=ledger --delta --type=time "--target=2026-10-01 03:00:00+00" --target-action=promote restore
sudo systemctl start postgresql@16-main
```

### 3. 복구 결과 확인

복구 인스턴스에 확인용 계정으로 붙어 마지막 거래 시각을 본다.

```sh
psql "postgresql://restore_check:{{secret:password16_2}}@ledger-db-restore.internal:5432/ledger" -c "select max(created_at) from ledger_entries;"
```

## 확인

- 마지막 거래 시각이 정한 시각 바로 앞이다.
- 서비스 담당이 표본 계정의 잔액을 확인했다.
- 운영 전환은 [ledger-db 장애 조치](ledger-db-failover.md)의 5단계처럼 DNS를 바꿔서 한다.
