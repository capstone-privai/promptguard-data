# Shipments: limits

A damaged return is quarantined and cannot increase sellable inventory.

Decision: amounts are bounded integer cents.

Reject negative quantities before computing extended line amounts.

The cancelled state is handled as follows: Cancellation before capture creates no movement in the ledger.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
