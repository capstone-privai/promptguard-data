# Refunds: limits

A return refers to its original capture, and the refundable balance cannot become negative.

Decision: amounts are bounded integer cents.

Reject negative quantities before computing extended line amounts.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
