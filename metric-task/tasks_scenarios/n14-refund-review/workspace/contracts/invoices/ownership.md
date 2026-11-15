# Invoices: ownership

Issued line amounts stay fixed even if the product catalog changes later.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The pending state is handled as follows: Unsettled entries remain visible but do not contribute to booked totals.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
