# Credits: failures

Credits expire in their original currency; expiry never creates a new charge.

Decision: retry only transient provider failures.

A completed request is final even if the caller lost its connection.

The cancelled state is handled as follows: Cancellation before capture creates no movement in the ledger.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
