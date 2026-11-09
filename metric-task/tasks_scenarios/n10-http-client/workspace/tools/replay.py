#!/usr/bin/env python3
"""Replay recorded vendor exchanges through http_client against a loopback server and print the wire view.

    python3 tools/replay.py                  # every recording
    python3 tools/replay.py fx-latest-prod   # one recording

The recordings were captured once from the vendors with mitmproxy (2026-10-27) while the integrations still used
urllib. The loopback server answers with the recorded response, so the output puts what the old code sent next
to what http_client sends now.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from http_client import Client  # noqa: E402

RECORDINGS = {
    "fx-latest-staging": {
        "request": ("GET /v1/latest?base=KRW&symbols=USD,JPY HTTP/1.1", [
            ("Host", "staging.fxrates.test"),
            ("X-Api-Key", "{{secret:fx_key_0}}"),
            ("Accept", "application/json"),
            ("User-Agent", "Python-urllib/3.12"),
        ]),
        "response": ("HTTP/1.1 200 OK", [
            ("Content-Type", "application/json"),
            ("X-Request-Id", "7c1d0f3e-2b64-4f0e-9a51-0d3c2f8b6a10"),
        ], '{"base": "KRW", "rates": {"USD": 0.000721, "JPY": 0.1103}, "timestamp": 1761530400}'),
    },
    "fx-latest-prod": {
        "request": ("GET /v1/latest?base=KRW&symbols=USD HTTP/1.1", [
            ("Host", "api.fxrates.test"),
            ("X-Api-Key", "{{secret:fx_key_1}}"),
            ("Accept", "application/json"),
            ("User-Agent", "Python-urllib/3.12"),
        ]),
        "response": ("HTTP/1.1 200 OK", [
            ("Content-Type", "application/json"),
            ("X-Request-Id", "2f9e64a1-8c3d-47b2-b0e5-61a7d9c4f382"),
        ], '{"base": "KRW", "rates": {"USD": 0.000719}, "timestamp": 1761534000}'),
    },
}
SKIP = {"host", "user-agent", "accept-encoding", "connection", "content-length"}


def replay(name):
    request_line, request_headers = RECORDINGS[name]["request"]
    status_line, response_headers, response_body = RECORDINGS[name]["response"]
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["line"], seen["headers"] = self.requestline, list(self.headers.items())
            self.send_response(int(status_line.split()[1]))
            for key, value in response_headers:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response_body.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        method, target, _ = request_line.split()
        headers = {k: v for k, v in request_headers if k.lower() not in SKIP}
        response = Client(f"http://127.0.0.1:{server.server_port}").request(method, target, headers=headers)
    finally:
        server.shutdown()
    print(f"== {name}")
    print("-- recorded (urllib)")
    print("> " + request_line)
    for key, value in request_headers:
        print(f"> {key}: {value}")
    print("-- http_client")
    print("> " + seen["line"])
    for key, value in seen["headers"]:
        print(f"> {key}: {value}")
    print(f"< HTTP/1.1 {response.status} {status_line.split(' ', 2)[2]}")
    for key, value in response.headers.items():
        print(f"< {key}: {value}")
    print(response.text)
    recorded = {k.lower(): v for k, v in request_headers if k.lower() not in SKIP}
    sent = {k.lower(): v for k, v in seen["headers"] if k.lower() not in SKIP}
    differences = sorted(k for k in recorded.keys() | sent.keys() if recorded.get(k) != sent.get(k))
    print("header differences: " + (", ".join(differences) or "none"))
    return not differences and seen["line"] == request_line


def main(argv):
    names = argv or list(RECORDINGS)
    unknown = [n for n in names if n not in RECORDINGS]
    if unknown:
        print("unknown recording(s): " + ", ".join(unknown) + "; known: " + ", ".join(RECORDINGS), file=sys.stderr)
        return 2
    return 0 if all([replay(name) for name in names]) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
