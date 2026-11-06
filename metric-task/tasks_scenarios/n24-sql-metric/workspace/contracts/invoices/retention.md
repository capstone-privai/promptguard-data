# Invoices: retention

Issued line amounts stay fixed even if the product catalog changes later.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The disputed state is handled as follows: An open dispute keeps its gross amount until the resolution arrives.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
