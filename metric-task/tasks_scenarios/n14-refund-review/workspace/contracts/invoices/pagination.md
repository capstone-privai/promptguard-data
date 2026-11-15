# Invoices: pagination

Issued line amounts stay fixed even if the product catalog changes later.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The returned state is handled as follows: Returns subtract the original amount, including the original rounding.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
