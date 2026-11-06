# Refunds: failures

A return refers to its original capture, and the refundable balance cannot become negative.

Decision: retry only transient provider failures.

A completed request is final even if the caller lost its connection.

The cancelled state is handled as follows: Cancellation before capture creates no movement in the ledger.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
