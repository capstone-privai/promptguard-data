# Customers: retention

Archived customers remain addressable by historical ledger movements.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The returned state is handled as follows: Returns subtract the original amount, including the original rounding.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
