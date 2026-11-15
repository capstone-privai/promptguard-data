# Ledger application
The supported import remains `from core import app`.
Public compute_* helpers accept mapping rows and an optional limit. Constants remain public too.
Run `python3 -m unittest discover -s tests -v`. Connection diagnostics are expected during those tests.
Preserve data ordering, input immutability and configuration values while splitting the module.
