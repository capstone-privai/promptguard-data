# Changelog

## 1.5.0 (2026-10-20)

- `GET /v1/customers/<id>/invoices`.
- Invoices can be `void`.
- `LEDGER_LOG_LEVEL` is case-insensitive.

## 1.5.0rc1 (2026-09-25)

- Customers have `display_name`.
- Client: `create_invoice(idempotency_key=...)`.
- Access log line per request.

## 1.4.0 (2026-09-05)

- `GET /v1/invoices` accepts `status`.
- Client: `Client.list_invoices(status=...)`.

## 1.3.0 (2026-07-21)

- `GET /v1/customers/<id>`.
