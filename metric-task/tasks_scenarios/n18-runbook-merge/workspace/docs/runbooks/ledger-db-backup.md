# ledger-db 백업

## 개요

ledger 데이터베이스 백업이 제대로 쌓이는지 확인하고, 빠졌을 때 수동으로 백업을 만드는 절차다.
백업 실패 알림(#ledger-alerts의 `backup_missing`)을 받으면 이 문서를 따른다.

## 사전 조건

- db-backup-01에 ssh로 들어갈 수 있어야 한다.
- 백업 저장소는 s3://ledger-backups/ 이다.

## 절차

### 1. 야간 덤프 확인

db-backup-01의 cron이 매일 02:00에 standby에서 덤프를 뜬다. 오늘 날짜 파일이 있는지 본다.

```sh
ls -lh /backups/ | tail -n 3
```

파일이 없으면 직접 덤프를 뜬다. standby에서 떠야 primary에 부하가 가지 않는다.

```sh
pg_dump -Fc -h ledger-db-replica.internal -U backup -f /backups/ledger-$(date +%F).dump ledger
aws s3 cp /backups/ledger-$(date +%F).dump s3://ledger-backups/dumps/
```

### 2. pgBackRest 백업 확인

stanza `ledger`의 마지막 전체 백업과 증분 백업 시각을 본다. 전체 백업은 일요일, 증분은 매일 01:00이다.

```sh
sudo -u postgres pgbackrest --stanza=ledger info
```

### 3. 수동 증분 백업

마지막 증분이 26시간보다 오래됐으면 수동으로 하나 만든다.

```sh
sudo -u postgres pgbackrest --stanza=ledger --type=incr backup
```

## 확인

- `pgbackrest --stanza=ledger info`의 마지막 백업 시각이 갱신됐다.
- #ledger-alerts의 `backup_missing` 알림이 해소됐다.
