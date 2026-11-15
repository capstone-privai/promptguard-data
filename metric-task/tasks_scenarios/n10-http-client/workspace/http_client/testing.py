"""Test helpers: a transport that records requests and answers from a queue, and a network guard."""
from __future__ import annotations
import contextlib
import json as _json
import socket
from unittest import mock

from http_client import Response


class NetworkBlocked(OSError):
    pass


class FakeTransport:
    def __init__(self):
        self.requests = []
        self._replies = []

    def queue(self, status: int = 200, *, json=None, body: bytes = b"", headers: dict | None = None) -> None:
        headers = dict(headers or {})
        if json is not None:
            body = _json.dumps(json).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        self._replies.append(Response(status, headers, body))

    def send(self, request):
        self.requests.append(request)
        if not self._replies:
            raise AssertionError(f"unexpected request: {request.method} {request.url}")
        reply = self._replies.pop(0)
        reply.url = request.url
        return reply

    @property
    def pending(self) -> int:
        return len(self._replies)


@contextlib.contextmanager
def block_network():
    """Any real connection attempt fails fast instead of reaching the vendor."""
    def refuse(address, *args, **kwargs):
        raise NetworkBlocked(f"tests must not open network connections (tried {address!r})")

    def no_dns(host, port, *args, **kwargs):
        raise NetworkBlocked(f"tests must not resolve hosts (tried {host}:{port})")

    with mock.patch.object(socket, "create_connection", refuse), mock.patch.object(socket, "getaddrinfo", no_dns):
        yield
