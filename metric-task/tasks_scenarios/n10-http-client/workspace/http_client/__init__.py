"""In-house HTTP client for integrations.

One place for base URLs, auth, timeouts, retries and request logs with credentials redacted. An integration
builds a Client per API and calls it; tests swap the transport (http_client.testing.FakeTransport).
See docs/http_client.md.
"""
from __future__ import annotations
import base64
import contextlib
from dataclasses import dataclass, field
import json as _json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

__all__ = ["BasicAuth", "BearerAuth", "Client", "HTTPError", "HeaderAuth", "QueryAuth", "Request", "Response",
           "SignedAuth", "TokenAuth", "TransportError", "current_transport", "use_transport"]

log = logging.getLogger("http_client")
SENSITIVE_HEADERS = frozenset({"authorization", "x-api-key", "dd-api-key", "signature", "cookie"})
SENSITIVE_PARAMS = frozenset({"access_token", "api_key", "token", "key"})


def redact_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if not parts.query:
        return url
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    query = "&".join(f"{k}=[REDACTED:{k.lower()}]" if k.lower() in SENSITIVE_PARAMS
                     else f"{k}={urllib.parse.quote(v, safe=',')}" for k, v in pairs)
    return urllib.parse.urlunsplit(parts._replace(query=query))


def redact_headers(headers: dict) -> dict:
    return {k.lower(): f"[REDACTED:{k.lower()}]" if k.lower() in SENSITIVE_HEADERS else v for k, v in headers.items()}


def _lookup(headers: dict, name: str, default=None):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return default


@dataclass
class Request:
    method: str
    url: str
    headers: dict = field(default_factory=dict)
    body: bytes | None = None
    timeout: float = 10.0

    def header(self, name: str, default=None):
        return _lookup(self.headers, name, default)

    def set_header(self, name: str, value: str) -> None:
        for key in [k for k in self.headers if k.lower() == name.lower()]:
            del self.headers[key]
        self.headers[name] = value

    def query(self) -> dict:
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.url).query, keep_blank_values=True)

    def json(self):
        return _json.loads(self.body) if self.body else None

    def form(self) -> dict:
        return dict(urllib.parse.parse_qsl(self.body.decode("utf-8"))) if self.body else {}


@dataclass
class Response:
    status: int
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    url: str = ""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.body) if self.body else None

    def header(self, name: str, default=None):
        return _lookup(self.headers, name, default)


class HTTPError(Exception):
    """A response with status >= 400 when the call asked for raise_for_status (the default)."""

    def __init__(self, request: Request, response: Response):
        super().__init__(f"{request.method} {redact_url(request.url)} returned HTTP {response.status}")
        self.request, self.response, self.status = request, response, response.status


class TransportError(Exception):
    """No response at all: DNS, connection refused, timeout."""


class HeaderAuth:
    """Sets one header on every request, e.g. HeaderAuth("DD-API-KEY", key)."""

    def __init__(self, name, value):
        self._name, self._value = name, value

    def __call__(self, request: Request) -> None:
        request.set_header(self._name, self._value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._name}: <redacted>)"


class TokenAuth(HeaderAuth):
    """Authorization: <scheme> <token>, e.g. TokenAuth("token", ...) for GitHub or ("GenieKey", ...)."""

    def __init__(self, scheme, credential):
        super().__init__("Authorization", f"{scheme} {credential}")


class BearerAuth(TokenAuth):
    def __init__(self, credential):
        super().__init__("Bearer", credential)


class BasicAuth(TokenAuth):
    def __init__(self, username, secret):
        super().__init__("Basic", base64.b64encode(f"{username}:{secret}".encode("utf-8")).decode("ascii"))


class QueryAuth:
    def __init__(self, param, value):
        self._param, self._value = param, value

    def __call__(self, request: Request) -> None:
        sep = "&" if urllib.parse.urlsplit(request.url).query else "?"
        request.url += sep + urllib.parse.urlencode({self._param: self._value})


class SignedAuth:
    """Calls sign(request) after the URL and body are final, so the callable can sign them and set headers."""

    def __init__(self, sign):
        self._sign = sign

    def __call__(self, request: Request) -> None:
        self._sign(request)


class UrllibTransport:
    def send(self, request: Request) -> Response:
        raw = urllib.request.Request(request.url, data=request.body, method=request.method, headers=request.headers)
        try:
            with urllib.request.urlopen(raw, timeout=request.timeout) as resp:
                return Response(resp.status, dict(resp.headers.items()), resp.read(), resp.geturl())
        except urllib.error.HTTPError as exc:
            return Response(exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read(), request.url)
        except (urllib.error.URLError, OSError) as exc:
            raise TransportError(f"{request.method} {redact_url(request.url)}: {exc}") from exc


_transport = UrllibTransport()


def current_transport():
    return _transport


@contextlib.contextmanager
def use_transport(transport):
    """Send every request of every Client through transport inside the block (tests, replay tools)."""
    global _transport
    previous, _transport = _transport, transport
    try:
        yield transport
    finally:
        _transport = previous


def _retry_after(response: Response) -> float | None:
    value = response.header("Retry-After")
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None


class Client:
    def __init__(self, base_url: str = "", *, auth=None, headers: dict | None = None, timeout: float = 10.0,
                 retries: int = 0, retry_on=(429, 502, 503, 504), backoff: float = 1.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.authenticator = auth
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.retries = retries
        self.retry_on = tuple(retry_on)
        self.backoff = backoff
        self.transport = transport

    def url(self, path: str = "", params=None) -> str:
        if path.startswith(("http://", "https://")):
            url = path
        elif path:
            url = self.base_url + "/" + path.lstrip("/")
        else:
            url = self.base_url
        if params:
            items = params.items() if isinstance(params, dict) else params
            query = urllib.parse.urlencode([(k, v) for k, v in items if v is not None], doseq=True)
            url += ("&" if "?" in url else "?") + query
        return url

    def request(self, method: str, path: str = "", *, params=None, json=None, data=None, form=None,
                headers: dict | None = None, auth=None, timeout: float | None = None,
                raise_for_status: bool = True) -> Response:
        merged = {**self.headers, **(headers or {})}
        body = None
        if json is not None:
            body = _json.dumps(json, ensure_ascii=False).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        elif form is not None:
            body = urllib.parse.urlencode(form, doseq=True).encode("ascii")
            merged.setdefault("Content-Type", "application/x-www-form-urlencoded")
        elif data is not None:
            body = data if isinstance(data, bytes) else str(data).encode("utf-8")
        request = Request(method.upper(), self.url(path, params), merged, body, timeout or self.timeout)
        signer = auth or self.authenticator
        if signer is not None:
            signer(request)
        attempt = 0
        while True:
            response = (self.transport or _transport).send(request)
            log.debug("%s %s -> %s %s", request.method, redact_url(request.url), response.status,
                      " ".join(f"{k}={v}" for k, v in sorted(redact_headers(request.headers).items())))
            if response.status in self.retry_on and attempt < self.retries:
                attempt += 1
                wait = _retry_after(response)
                time.sleep(self.backoff * 2 ** (attempt - 1) if wait is None else wait)
                continue
            break
        if raise_for_status and response.status >= 400:
            raise HTTPError(request, response)
        return response

    def get(self, path: str = "", **kwargs) -> Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str = "", **kwargs) -> Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str = "", **kwargs) -> Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str = "", **kwargs) -> Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str = "", **kwargs) -> Response:
        return self.request("DELETE", path, **kwargs)

    def get_json(self, path: str = "", **kwargs):
        return self.request("GET", path, **kwargs).json()

    def post_json(self, path: str, payload, **kwargs):
        return self.request("POST", path, json=payload, **kwargs).json()
