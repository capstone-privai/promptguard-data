# orderdesk platform

Python monorepo for the order desk back office.

- `integrations/`: one module per vendor or partner API
- `http_client/`: the in-house HTTP client, see `docs/http_client.md`
- `auth/signer.py`: Ed25519 request signing for partner APIs
- `tools/replay.py`: replays recorded vendor exchanges through http_client on a loopback server

Tests never touch the network: `python3 -m unittest discover -s tests`. They record requests through
`http_client.testing.FakeTransport`, and a real connection attempt fails with `NetworkBlocked`.

## MIG-77: urllib to http_client

Every integration should call vendors through http_client, so that retries, timeouts and redacted request logs
live in one place. `integrations/github.py` was moved first (see `git log`). The test suite was switched to
FakeTransport afterwards, so a module that still calls urllib fails its tests.

Keep each module's public functions and behaviour as they are: the same requests on the wire, return values,
raised errors and retry counts. `tools/replay.py` shows what http_client sends for a recorded exchange.
