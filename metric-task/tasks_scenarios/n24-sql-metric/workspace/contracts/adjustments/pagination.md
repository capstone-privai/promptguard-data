# Adjustments: pagination

Manual adjustments require a reason and retain their original signed amount.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
