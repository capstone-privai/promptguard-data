# Transfers: pagination

The debit and credit legs share a sequence and must reconcile exactly.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The cancelled state is handled as follows: Cancellation before capture creates no movement in the ledger.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
