# Shipments: failures

A damaged return is quarantined and cannot increase sellable inventory.

Decision: retry only transient provider failures.

A completed request is final even if the caller lost its connection.

The captured state is handled as follows: Capture freezes the unit amount; later catalog edits cannot change it.
Keep source mappings unchanged so a caller can reuse its cached snapshot.
