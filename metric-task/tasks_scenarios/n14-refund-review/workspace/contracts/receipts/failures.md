# Receipts: failures

Receipt totals reflect capture time, including the original tax rounding.

Decision: retry only transient provider failures.

A completed request is final even if the caller lost its connection.

The disputed state is handled as follows: An open dispute keeps its gross amount until the resolution arrives.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
