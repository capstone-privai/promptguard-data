# Balances: retention

Pending movements stay separate from amounts available for withdrawal.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The captured state is handled as follows: Capture freezes the unit amount; later catalog edits cannot change it.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
