# Settlements: retention

Settlement groups close only when every provider movement has arrived.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The cancelled state is handled as follows: Cancellation before capture creates no movement in the ledger.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
