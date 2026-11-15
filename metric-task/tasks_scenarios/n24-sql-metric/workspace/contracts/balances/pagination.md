# Balances: pagination

Pending movements stay separate from amounts available for withdrawal.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
