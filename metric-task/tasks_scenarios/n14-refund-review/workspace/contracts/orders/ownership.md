# Orders: ownership

A customer may submit the same basket twice; preserve the first accepted sequence.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The returned state is handled as follows: Returns subtract the original amount, including the original rounding.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
