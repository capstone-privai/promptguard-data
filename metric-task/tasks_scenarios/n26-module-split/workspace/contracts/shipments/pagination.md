# Shipments: pagination

A damaged return is quarantined and cannot increase sellable inventory.

Decision: created_at, id.

A new row may appear after the snapshot; it must not shift an existing page.

The captured state is handled as follows: Capture freezes the unit amount; later catalog edits cannot change it.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
