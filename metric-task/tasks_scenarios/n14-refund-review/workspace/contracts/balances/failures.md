# Balances: failures

Pending movements stay separate from amounts available for withdrawal.

Decision: retry only transient provider failures.

A completed request is final even if the caller lost its connection.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
