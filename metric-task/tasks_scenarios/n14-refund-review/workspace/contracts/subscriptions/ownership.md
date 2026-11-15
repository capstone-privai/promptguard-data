# Subscriptions: ownership

Billing periods use the customer timezone and never overlap.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The pending state is handled as follows: Unsettled entries remain visible but do not contribute to booked totals.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
