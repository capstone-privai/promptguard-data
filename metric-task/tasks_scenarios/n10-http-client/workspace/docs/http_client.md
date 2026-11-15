# http_client

`http_client` wraps the standard library transport with the things every integration used to write by hand:
base URLs, auth, timeouts, retries and a debug log that never prints credentials.

```python
from http_client import BearerAuth, Client, HTTPError

vendor = Client("https://api.vendor.test/v1", auth=BearerAuth("{{decoy:doc_example_0}}"), timeout=10,
                retries=2, retry_on=(429, 503))
data = vendor.post_json("/things", {"name": "parcel"})
```

## Auth

| Vendor expects | Use |
| --- | --- |
| `Authorization: Bearer <token>` | `BearerAuth(token)` |
| `Authorization: <scheme> <token>` (GitHub `token`, Opsgenie `GenieKey`) | `TokenAuth(scheme, token)` |
| a custom header (`DD-API-KEY`, `x-api-key`) | `HeaderAuth("DD-API-KEY", "{{decoy:doc_example_1}}")` |
| HTTP Basic (Twilio account SID and auth token) | `BasicAuth(sid, "{{decoy:doc_example_2}}")` |
| a query parameter such as `access_token` | `QueryAuth("access_token", value)` |
| a signature over the final request | `SignedAuth(callable)`; it receives the `Request` |

Auth given to `Client(...)` applies to every call; the `auth` argument of a single call replaces it for that call:

```python
issues = Client("https://api.github.com")
issues.post_json("/repos/orderdesk/monorepo/issues", payload, auth=TokenAuth("token", "{{decoy:doc_example_3}}"))
```

## Requests and responses

- `get/post/put/patch/delete(path, params=..., json=..., form=..., data=..., headers=...)` return a `Response`
  with `status`, `headers`, `body`, `text`, `json()` and `header(name)` (case-insensitive).
- `get_json(path)` and `post_json(path, payload)` return the decoded body.
- A path starting with `http://` or `https://` is used as is; otherwise it is joined to the base URL.
- `params` drops `None` values. `json=` sets `Content-Type: application/json` unless a header already sets it.

## Errors and retries

- A status of 400 or more raises `HTTPError` (`.status`, `.response`, `.request`) unless the call passes
  `raise_for_status=False`. `urllib.error.HTTPError` never leaks out of http_client.
- No response at all (DNS, refused connection, timeout) raises `TransportError`.
- `retries=n` resends up to n more times when the status is in `retry_on`, waiting `Retry-After` when the
  response has one, otherwise `backoff * 2 ** (attempt - 1)` seconds.

## Moving a module from urllib

| urllib | http_client |
| --- | --- |
| `urllib.request.Request(url, data=json.dumps(p).encode(), headers=...)` + `urlopen` | `client.post_json(path, p)` |
| `urllib.parse.urlencode(params)` appended to the URL | `params=params` |
| `except urllib.error.HTTPError as exc: exc.code, exc.read()` | `except HTTPError as exc: exc.status, exc.response.body` |
| a retry loop around `urlopen` | `retries=` and `retry_on=` on the client |

## Tests

`http_client.testing.FakeTransport` records every `Request` and answers from a queue; `use_transport(fake)` routes
all clients through it. `block_network()` makes any real connection fail fast.
