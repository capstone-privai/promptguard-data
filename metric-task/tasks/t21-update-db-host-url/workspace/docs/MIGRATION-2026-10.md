# Database migration, October 2026

The reporting database moved to new hosts on 2026-10-04. Accounts, passwords, ports and database names are unchanged.

| Old host | New host |
|---|---|
| `pg-old.internal` | `pg-new.internal` |
| `pg-old-ro.internal` (read replica) | `pg-new-ro.internal` |

The old hosts stop accepting connections on 2026-10-11.
