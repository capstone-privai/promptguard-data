# Transfers: retention

The debit and credit legs share a sequence and must reconcile exactly.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
