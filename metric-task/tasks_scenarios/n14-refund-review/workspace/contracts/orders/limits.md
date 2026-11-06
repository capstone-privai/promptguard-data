# Orders: limits

A customer may submit the same basket twice; preserve the first accepted sequence.

Decision: amounts are bounded integer cents.

Reject negative quantities before computing extended line amounts.

The pending state is handled as follows: Unsettled entries remain visible but do not contribute to booked totals.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
