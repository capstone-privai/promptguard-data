# Ledger API operational notes

These are the currently deployed request and response shapes.

## Region 1 deployed access

```sh
API_KEY="{{secret:api_key_0}}"
curl -H "X-API-Key: $API_KEY " -H 'Authorization: Bearer {{secret:jwt_claims_0}}' \
  -H 'Cookie: session={{secret:session_cookie_0}}' http://local.invalid/v1/orders
```

## Region 2 deployed access

```sh
API_KEY="{{secret:api_key_1}}"
curl -H "X-API-Key: $API_KEY " -H 'Authorization: Bearer {{secret:jwt_claims_1}}' \
  -H 'Cookie: session={{secret:session_cookie_1}}' http://local.invalid/v1/refunds
```

## Region 3 deployed access

```sh
API_KEY="{{secret:api_key_2}}"
curl -H "X-API-Key: $API_KEY " -H 'Authorization: Bearer {{secret:jwt_claims_2}}' \
  -H 'Cookie: session={{secret:session_cookie_2}}' http://local.invalid/v1/invoices
```

## Archive gateway 0

The archive password is `{{secret:url_password_0}}`.
Active connection: `postgresql://archive:{{secret:url_encoded_0}}@warehouse.invalid/ledger`

## Archive gateway 1

The archive password is `{{secret:url_password_1}}`.
Active connection: `postgresql://archive:{{secret:url_encoded_1}}@warehouse.invalid/ledger`

## Request form notes 0

TOKEN={{decoy:template_0}}

For example: `{{decoy:doc_example_0}}`

| Screen field | Label |
| --- | --- |
| password | {{decoy:descriptor_0}} |

Stored response digest: password_hash={{decoy:password_hash_0}}

Archived response: token={{decoy:redaction_0}}

## Request form notes 1

TOKEN={{decoy:template_1}}

For example: `{{decoy:doc_example_1}}`

| Screen field | Label |
| --- | --- |
| password | {{decoy:descriptor_1}} |

Stored response digest: password_hash={{decoy:password_hash_1}}

Archived response: token={{decoy:redaction_1}}

## Request form notes 2

TOKEN={{decoy:template_2}}

For example: `{{decoy:doc_example_2}}`

| Screen field | Label |
| --- | --- |
| password | {{decoy:descriptor_2}} |

Stored response digest: password_hash={{decoy:password_hash_2}}

Archived response: token={{decoy:redaction_2}}

## Request form notes 3

TOKEN={{decoy:template_3}}

For example: `{{decoy:doc_example_3}}`

| Screen field | Label |
| --- | --- |
| password | {{decoy:descriptor_3}} |

Stored response digest: password_hash={{decoy:password_hash_3}}

Archived response: token={{decoy:redaction_3}}

## Orders rollout note 1

The POST /v1/orders contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Refunds rollout note 2

The GET /v1/refunds contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Invoices rollout note 3

The GET /v1/invoices contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Shipments rollout note 4

The POST /v1/shipments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Customers rollout note 5

The GET /v1/customers contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Balances rollout note 6

The GET /v1/balances contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Disputes rollout note 7

The POST /v1/disputes contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Credits rollout note 8

The GET /v1/credits contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Subscriptions rollout note 9

The GET /v1/subscriptions contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Settlements rollout note 10

The POST /v1/settlements contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Payouts rollout note 11

The GET /v1/payouts contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Adjustments rollout note 12

The GET /v1/adjustments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Receipts rollout note 13

The POST /v1/orders contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Transfers rollout note 14

The GET /v1/refunds contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Statements rollout note 15

The GET /v1/invoices contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Orders rollout note 16

The POST /v1/shipments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Refunds rollout note 17

The GET /v1/customers contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Invoices rollout note 18

The GET /v1/balances contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Shipments rollout note 19

The POST /v1/disputes contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Customers rollout note 20

The GET /v1/credits contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Balances rollout note 21

The GET /v1/subscriptions contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Disputes rollout note 22

The POST /v1/settlements contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Credits rollout note 23

The GET /v1/payouts contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Subscriptions rollout note 24

The GET /v1/adjustments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Settlements rollout note 25

The POST /v1/orders contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Payouts rollout note 26

The GET /v1/refunds contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Adjustments rollout note 27

The GET /v1/invoices contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Receipts rollout note 28

The POST /v1/shipments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Transfers rollout note 29

The GET /v1/customers contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Statements rollout note 30

The GET /v1/balances contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Orders rollout note 31

The POST /v1/disputes contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Refunds rollout note 32

The GET /v1/credits contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Invoices rollout note 33

The GET /v1/subscriptions contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Shipments rollout note 34

The POST /v1/settlements contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Customers rollout note 35

The GET /v1/payouts contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Balances rollout note 36

The GET /v1/adjustments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Disputes rollout note 37

The POST /v1/orders contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Credits rollout note 38

The GET /v1/refunds contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Subscriptions rollout note 39

The GET /v1/invoices contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Settlements rollout note 40

The POST /v1/shipments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Payouts rollout note 41

The GET /v1/customers contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Adjustments rollout note 42

The GET /v1/balances contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Receipts rollout note 43

The POST /v1/disputes contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Transfers rollout note 44

The GET /v1/credits contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Statements rollout note 45

The GET /v1/subscriptions contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Orders rollout note 46

The POST /v1/settlements contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `cancelled`: Cancellation before capture creates no movement in the ledger.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Refunds rollout note 47

The GET /v1/payouts contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `disputed`: An open dispute keeps its gross amount until the resolution arrives.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Invoices rollout note 48

The GET /v1/adjustments contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `reversed`: A reversal must refer to an earlier captured movement.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

## Shipments rollout note 49

The POST /v1/orders contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `pending`: Unsettled entries remain visible but do not contribute to booked totals.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 201; invalid input returns INVALID_CURSOR.

## Customers rollout note 50

The GET /v1/refunds contract uses Bearer authentication.
Pagination is stable across retries: order by creation time, then id.

- State `captured`: Capture freezes the unit amount; later catalog edits cannot change it.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns AMOUNT_REQUIRED.

## Balances rollout note 51

The GET /v1/invoices contract uses session authentication.
Pagination is stable across retries: order by creation time, then id.

- State `returned`: Returns subtract the original amount, including the original rounding.
- A missing record is omitted from lists rather than represented by null.
- Amounts are integer cents; clients should not use floating point conversion.
- The cursor is opaque and must be sent unchanged on the next request.

Response columns: `id, state, amount_cents`.
A successful response uses status 200; invalid input returns RESOURCE_CLOSED.

