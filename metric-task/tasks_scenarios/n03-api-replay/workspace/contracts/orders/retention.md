# Orders: retention

A customer may submit the same basket twice; preserve the first accepted sequence.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The pending state is handled as follows: Unsettled entries remain visible but do not contribute to booked totals.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
