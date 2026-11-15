# Ledger API v1

All amounts are integers in the currency's minor unit (KRW and JPY have none; USD and EUR use cents).

## GET /v1/invoices

Query: `offset` (default 0), `limit` (default `LEDGER_PAGE_SIZE`, at most `LEDGER_PAGE_SIZE_MAX`), `status`.
Response: `{"items": [invoice...], "total_count": n}`. Invoices are ordered by `issued_at`, then `id`.
To read everything, repeat with `offset` increased by `limit` until `offset >= total_count`.

Invoice: `id`, `customer_id`, `total_cents` (integer), `currency`, `status`, `issued_at`.

`status` is `open` until the invoice is fully paid, then `paid`. `POST /v1/invoices/<id>/void` sets an open invoice to `void` (400 for any other status).

## POST /v1/invoices

Body: `customer_id`, `total` (integer, must not be negative), `currency` (KRW, USD, EUR or JPY; default
`LEDGER_DEFAULT_CURRENCY`).
Returns 201 and the invoice. Invalid input returns 400.

## GET /v1/invoices/<id>

Returns the invoice, or 404 when the id is unknown.

## GET /v1/invoices/<id>/payments

Response: `{"items": [payment...]}`. Payment: `id`, `invoice_id`, `amount` (decimal string in major units, e.g. `"12.50"`), `currency`, `method`.

## GET /v1/customers/<id>/invoices

Response: `{"items": [invoice...]}` ordered by `issued_at`.

## GET /v1/customers/<id>

Customer: `id`, `display_name`, `name` (same as `display_name`, kept for 1.x clients), `email`. Returns 404 when the id is unknown.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `LEDGER_DATABASE_URL` | required | storage location (`memory://<name>` for the in-memory store) |
| `LEDGER_PAGE_SIZE` | 20 | default `page_size` |
| `LEDGER_PAGE_SIZE_MAX` | 100 | upper bound for `page_size` |
| `LEDGER_LOG_LEVEL` | INFO | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `LEDGER_DEFAULT_CURRENCY` | KRW | currency for invoices created without one |
