# Balances: ownership

Pending movements stay separate from amounts available for withdrawal.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The cancelled state is handled as follows: Cancellation before capture creates no movement in the ledger.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
