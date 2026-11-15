"""Run the WSGI app in-process; wsgi_opener lets ledger_client talk to it without a socket."""
import io
import json
from urllib.parse import urlsplit

from ledger.app import LedgerApp
from ledger.settings import load
from ledger.store import sample_store

TEST_ENV = {"LEDGER_DATABASE_URL": "memory://tests"}


def make_app(**env):
    return LedgerApp(sample_store(), load({**TEST_ENV, **env}))


def call(app, method, path, query="", body=None, headers=None):
    data = b"" if body is None else json.dumps(body).encode()
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": query,
               "CONTENT_LENGTH": str(len(data)), "wsgi.input": io.BytesIO(data)}
    for name, value in (headers or {}).items():
        environ["HTTP_" + name.upper().replace("-", "_")] = value
    seen = {}

    def start_response(status, response_headers):
        seen["status"] = int(status.split()[0])

    payload = b"".join(app(environ, start_response))
    return seen["status"], json.loads(payload)


class _Response:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def wsgi_opener(app, seen=None):
    def open_request(request, timeout=None):
        parts = urlsplit(request.full_url)
        body = json.loads(request.data) if request.data else None
        headers = {name: value for name, value in request.header_items()}
        if seen is not None:
            seen.append((request.get_method(), parts.path, parts.query, headers))
        status, payload = call(app, request.get_method(), parts.path, parts.query, body, headers)
        return _Response(status, json.dumps(payload).encode())
    return open_request
