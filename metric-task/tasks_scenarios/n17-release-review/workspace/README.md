# ledger

Ledger HTTP API (v1) and its Python client. Standard library only.

```sh
python3 -m unittest discover -s tests -v
LEDGER_DATABASE_URL=memory://local python3 -m ledger.server     # http://127.0.0.1:8080
```

Authentication is terminated by the gateway in front of the service; the client sends a bearer token and the
service trusts the gateway. What counts as a breaking change is defined in `docs/COMPATIBILITY.md`.
