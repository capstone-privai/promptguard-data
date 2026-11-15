# Customers: pagination

Archived customers remain addressable by historical ledger movements.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The pending state is handled as follows: Unsettled entries remain visible but do not contribute to booked totals.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
