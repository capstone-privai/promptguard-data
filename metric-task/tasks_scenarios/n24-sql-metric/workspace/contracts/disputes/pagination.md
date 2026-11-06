# Disputes: pagination

The original capture remains booked until the dispute is resolved.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The disputed state is handled as follows: An open dispute keeps its gross amount until the resolution arrives.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
