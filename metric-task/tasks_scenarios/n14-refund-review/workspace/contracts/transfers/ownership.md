# Transfers: ownership

The debit and credit legs share a sequence and must reconcile exactly.

Decision: the ledger team owns movements.

The product team owns labels, descriptions and display preferences.

The captured state is handled as follows: Capture freezes the unit amount; later catalog edits cannot change it.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
