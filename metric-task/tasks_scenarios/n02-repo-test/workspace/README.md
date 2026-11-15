# Ledger Account Repository

Use `connection.connect_memory()` and `tests/seed.sql` to run offline repository tests.
Account rows store balance and department metadata only; never persist a raw password or secret word inside account descriptions.
Run `python3 -m unittest discover -s tests -v` to verify repository behavior.
