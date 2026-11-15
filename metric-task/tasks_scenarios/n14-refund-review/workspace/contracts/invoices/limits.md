# Invoices: limits

Issued line amounts stay fixed even if the product catalog changes later.

Decision: amounts are bounded integer cents.

Reject negative quantities before computing extended line amounts.

The disputed state is handled as follows: An open dispute keeps its gross amount until the resolution arrives.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
