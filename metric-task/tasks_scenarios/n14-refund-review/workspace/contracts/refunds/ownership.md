# Refunds: ownership

A return refers to its original capture, and the refundable balance cannot become negative.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The captured state is handled as follows: Capture freezes the unit amount; later catalog edits cannot change it.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
