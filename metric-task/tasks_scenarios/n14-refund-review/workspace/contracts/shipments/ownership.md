# Shipments: ownership

A damaged return is quarantined and cannot increase sellable inventory.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The reversed state is handled as follows: A reversal must refer to an earlier captured movement.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
