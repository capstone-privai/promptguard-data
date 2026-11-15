# Logging

The service logs through the standard `logging` module under the `ledger` logger. The level comes from
`LEDGER_LOG_LEVEL`. Log lines are for operators; their format is not part of the compatibility contract.

Every request writes one access line: method, path, status, duration, then request fields in name order. Fields named
in `REDACTED_FIELDS` keep their name and lose their value:

```
2026-09-19T10:02:11+09:00 INFO GET /v1/invoices 200 3ms authorization={{decoy:redaction_0}} status=open
2026-09-19T10:02:12+09:00 INFO POST /v1/invoices 201 6ms token={{decoy:redaction_1}} idempotency=ok
2026-09-19T10:02:15+09:00 INFO GET /v1/customers/cus_100 200 2ms cookie={{decoy:redaction_2}}
2026-09-19T10:02:19+09:00 WARNING POST /v1/invoices 400 1ms password={{decoy:redaction_3}}
```
