# ledger-ops

ledger 서비스 운영 저장소다. 인벤토리, 운영 문서, 결정 기록을 둔다.

## 운영 문서

- [ledger-db 장애 조치](docs/runbooks/ledger-db-failover.md)
- [ledger-db 백업](docs/runbooks/ledger-db-backup.md)
- [ledger-db 복구](docs/runbooks/ledger-db-restore.md)
- [queue 복구](docs/runbooks/queue-recovery.md)
- [queue 확장](docs/runbooks/queue-scaling.md)
- [gateway 인증서](docs/runbooks/gateway-certs.md)
- [gateway 롤백](docs/runbooks/gateway-rollback.md)
- [gateway 요청 한도](docs/runbooks/gateway-rate-limits.md)

문서 규칙은 [docs/STYLE.md](docs/STYLE.md), 결정 기록은 [docs/decisions/](docs/decisions/0012-pgbackrest.md)부터 본다.

## 검사

```sh
python3 tools/check_docs.py
```
