# 0012. ledger-db 백업을 pgBackRest로 옮긴다

- 상태: 채택 (2026-08-04)
- 관련 절차: [ledger-db 백업](../runbooks/ledger-db-backup.md), [ledger-db 복구](../runbooks/ledger-db-restore.md)

## 배경

db-backup-01의 야간 `pg_dump`는 데이터가 400GB를 넘으면서 4시간 넘게 걸리고, 덤프 시각으로만 되돌릴 수 있었다.

## 결정

pgBackRest로 주 1회 전체 백업, 매일 증분 백업, WAL 보관을 한다. 복구는 pgBackRest 시점 복구로 한다.
`pg_dump` cron과 db-backup-01은 2026-09-01에 없앴고, 덤프 파일은 더 만들지 않는다.

## 결과

복구 절차는 `pgbackrest restore --type=time`만 쓴다. 덤프 파일로 복구하는 절차는 쓰지 않는다.
