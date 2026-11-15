# Refunds: retention

A return refers to its original capture, and the refundable balance cannot become negative.

Decision: closed periods are immutable.

Archive the presentation record without deleting its accounting movements.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
