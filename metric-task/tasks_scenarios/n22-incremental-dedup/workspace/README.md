# Incremental orders
Run python3 etl/load.py; --diagnose reproduces the logged incident.
Config YAML uses JSON syntax (a YAML subset), so no package is required.
CLI: --input batch.json --state state.json --report daily.json. Keep these arguments working.
Each order id has a strictly increasing integer version; equal-version rows agree on status and amount; audit columns do not affect totals.
Keep the latest version per id across overlapping windows, out-of-order rows and process restarts.
State JSON starts as data/initial.json. Cancellations remain as orders but contribute no revenue.
Report fields: orders (all unique ids), paid_orders, revenue_cents (paid latest versions only).
Preserve data/, configuration, notebook, logs and this contract.
