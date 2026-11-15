# Payouts: failures

A bank rejection restores the pending payout without duplicating a movement.

Decision: retry only transient provider failures.

A completed request is final even if the caller lost its connection.

The pending state is handled as follows: Unsettled entries remain visible but do not contribute to booked totals.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
