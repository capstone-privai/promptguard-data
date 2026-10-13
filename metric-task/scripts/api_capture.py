"""Records what Claude Code sends to the Anthropic API during one metric-task run, and finds secrets in it.

The transcript shows the rows of the conversation as the mod left them, but not everything that leaves the
machine: the system prompt (git status, CLAUDE.md, environment), the tool definitions, an appended system prompt,
and the side requests Claude Code makes (title, summaries, token counting) are not transcript rows. To see what the
server received, the runner points Claude Code at this proxy (ANTHROPIC_BASE_URL) and the proxy relays every
request unchanged to the real API, keeping a copy of each request body.

What is kept: method, path, status, the model and a few protocol headers, and the request body. Credentials
(authorization, x-api-key, cookies) are never written. Responses are relayed (streamed) but not kept: whatever the
server sends back, it already had.

  CaptureProxy(path).start() -> base URL; .stop() writes <path> (JSON lines, xz-compressed)
  load(path) -> requests;  scan(requests, forms) -> what secret left in which request, through which channel

Standard library only.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import lzma
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
              "transfer-encoding", "upgrade", "host", "content-length"}
KEPT_HEADERS = {"anthropic-beta", "anthropic-version", "x-app", "user-agent", "x-stainless-helper-method"}
# Text the client itself sent. assistant_* rows are the model's own earlier output, sent back as history.
ECHO_CHANNELS = {"assistant_text", "assistant_tool_input"}


class CaptureProxy:
    def __init__(self, out_path: Path, upstream: str = "https://api.anthropic.com"):
        self.out_path = Path(out_path)
        self.upstream = urlsplit(upstream.rstrip("/"))
        self.records: list[dict] = []
        self.lock = threading.Lock()
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> str:
        proxy = self

        class Handler(_Handler):
            owner = proxy

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def add(self, record: dict):
        with self.lock:
            record["i"] = len(self.records)
            self.records.append(record)

    def stop(self) -> int:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        with self.lock:
            records = list(self.records)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with lzma.open(self.out_path, "wt", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return len(records)

    def connection(self) -> http.client.HTTPConnection:
        cls = http.client.HTTPSConnection if self.upstream.scheme == "https" else http.client.HTTPConnection
        return cls(self.upstream.hostname, self.upstream.port, timeout=900)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    owner: CaptureProxy

    def log_message(self, _format, *_args):
        return

    def read_body(self) -> bytes:
        if self.headers.get("transfer-encoding", "").lower() == "chunked":
            parts = []
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    break
                parts.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(parts)
        length = int(self.headers.get("content-length") or 0)
        return self.rfile.read(length) if length else b""

    def relay(self):
        body = self.read_body()
        record = {"t": round(time.time(), 3), "method": self.command, "path": self.path,
                  "headers": {k.lower(): v for k, v in self.headers.items() if k.lower() in KEPT_HEADERS},
                  "body": body.decode("utf-8", errors="replace"), "status": None}
        try:
            body_json = json.loads(body) if body else None
            if isinstance(body_json, dict):
                record["model"] = body_json.get("model")
        except ValueError:
            pass
        conn = self.owner.connection()
        try:
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            headers["Host"] = self.owner.upstream.netloc
            conn.request(self.command, (self.owner.upstream.path or "") + self.path, body=body or None,
                         headers=headers)
            resp = conn.getresponse()
            record["status"] = resp.status
            self.send_response_only(resp.status, resp.reason)  # upstream's own Date and Server headers follow
            for k, v in resp.getheaders():
                if k.lower() not in HOP_BY_HOP:
                    self.send_header(k, v)
            no_body = self.command == "HEAD" or resp.status in (204, 304) or 100 <= resp.status < 200
            if no_body:
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                while True:
                    chunk = resp.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
                    self.wfile.flush()
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except Exception as e:  # upstream unreachable: the client sees a 502 and the run is an API failure
            record["error"] = f"{type(e).__name__}: {e}"[:300]
            if record["status"] is None:
                payload = json.dumps({"type": "error", "error": {"type": "api_error",
                                                                 "message": "metric2 capture proxy: " + record["error"]}}).encode()
                self.send_response(502)
                self.send_header("content-type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            self.close_connection = True
        finally:
            conn.close()
            self.owner.add(record)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = relay


# ---- reading and scanning ----------------------------------------------------------------------------------

def load(path: Path) -> list[dict]:
    path = Path(path)
    if not path.is_file():
        return []
    with lzma.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _strings(value, out: list[str]):
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, list):
        for v in value:
            _strings(v, out)
    elif isinstance(value, dict):
        for v in value.values():
            _strings(v, out)
    return out


def texts(body) -> list[tuple[str, str, str]]:
    """(channel, tool, text) for each piece of text in a Messages API request body.

    system               the system prompt (Claude Code's instructions, environment, git status, CLAUDE.md
                         when it goes there, an appended system prompt)
    tools                tool definitions (names, descriptions, MCP server instructions)
    user_text            text the user turn carries: the prompt, stdin
    reminder             <system-reminder> text in a user turn: CLAUDE.md, attachments, hook output
    tool_result          a tool's result; tool names the tool that produced it
    assistant_text       the model's own earlier text and thinking, sent back as history (echo)
    assistant_tool_input the model's own earlier tool arguments (echo)
    other                any other field
    """
    if not isinstance(body, dict):
        return [("raw", "", body if isinstance(body, str) else json.dumps(body))]
    out = []
    for key, value in body.items():
        if key == "messages":
            continue
        if key == "system":
            out += [("system", "", s) for s in _strings(value, [])]
        elif key == "tools":
            out += [("tools", "", s) for s in _strings(value, [])]
        elif key not in ("model", "max_tokens", "stream", "temperature", "thinking", "metadata"):
            out += [("other", key, s) for s in _strings(value, [])]
    names: dict[str, str] = {}
    for message in body.get("messages") or []:
        if not isinstance(message, dict):
            continue
        role, content = message.get("role"), message.get("content")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if role == "assistant":
                if kind == "tool_use":
                    names[block.get("id")] = block.get("name") or "?"
                    out += [("assistant_tool_input", block.get("name") or "?", s) for s in _strings(block.get("input"), [])]
                else:
                    out += [("assistant_text", "", s) for s in _strings({k: v for k, v in block.items()
                                                                         if k in ("text", "thinking")}, [])]
            elif kind == "tool_result":
                tool = names.get(block.get("tool_use_id"), "?")
                out += [("tool_result", tool, s) for s in _strings(block.get("content"), [])]
            elif kind == "text":
                text = block.get("text") or ""
                out.append(("reminder" if text.lstrip().startswith("<system-reminder>") else "user_text", "", text))
            else:
                out += [("user_other", kind or "?", s) for s in _strings(block, [])]
    return out


def partial_windows(value: str) -> list[str]:
    """Substrings that show a meaningful part of a secret: half its length, at least 10 characters."""
    if len(value) < 16:
        return []
    size = max(10, len(value) // 2)
    step = max(1, size // 4)
    return [value[i:i + size] for i in range(0, len(value) - size + 1, step)]


def scan(requests: list[dict], forms: list[tuple[str, str, str]]) -> dict:
    """Where each secret shows up in what the client sent.

    forms: (root secret, how, text) from m2_tasks.leak_forms. A hit in a channel outside ECHO_CHANNELS means the
    client sent the secret; echo-only hits are the model repeating something it was sent (or decoded) earlier.
    Partial hits (half of a secret or more, no full form in the same text) are reported apart.
    """
    roots = sorted({root for root, _, _ in forms})
    windows = {root: [w for _r, how, text in forms if _r == root and how == "exact" for w in partial_windows(text)]
               for root in roots}
    hits: dict[str, dict] = {}       # root -> {"channels": set, "tools": set, "how": set, "first": i}
    partial: dict[str, set] = {}     # root -> channels
    echo: dict[str, set] = {}
    cache: dict[str, list] = {}
    models, paths, statuses = set(), {}, {}
    requests_with_leak = 0
    for req in requests:
        paths[req.get("path", "?").split("?")[0]] = paths.get(req.get("path", "?").split("?")[0], 0) + 1
        statuses[str(req.get("status"))] = statuses.get(str(req.get("status")), 0) + 1
        if req.get("model"):
            models.add(req["model"])
        raw = req.get("body") or ""
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = raw
        leaked_here = False
        for channel, tool, text in texts(body) if body is not None else []:
            key = hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()
            if key not in cache:
                found = [(root, how) for root, how, form in forms if form in text]
                full = {root for root, _ in found}
                part = [root for root in roots if root not in full and any(w in text for w in windows[root])]
                cache[key] = [found, part]
            found, part = cache[key]
            for root, how in found:
                if channel in ECHO_CHANNELS:
                    echo.setdefault(root, set()).add(channel)
                    continue
                leaked_here = True
                h = hits.setdefault(root, {"channels": set(), "tools": set(), "how": set(), "first": req.get("i")})
                h["channels"].add(channel)
                h["how"].add(how)
                if tool:
                    h["tools"].add(tool)
            for root in part:
                if channel not in ECHO_CHANNELS:
                    partial.setdefault(root, set()).add(channel)
        requests_with_leak += leaked_here
    channels = sorted({c for h in hits.values() for c in h["channels"]})
    return {
        "requests": len(requests), "paths": paths, "statuses": statuses, "models": sorted(models),
        "secrets_total": len(roots),
        "leaked": sorted(hits), "leaked_count": len(hits),
        "channels": channels,
        "by_secret": {root: {"channels": sorted(h["channels"]), "tools": sorted(h["tools"]),
                             "how": sorted(h["how"]), "first_request": h["first"]} for root, h in sorted(hits.items())},
        "encoded_only": sorted(root for root, h in hits.items() if "exact" not in h["how"]),
        "partial_only": sorted(root for root in partial if root not in hits),
        "echo_only": sorted(root for root in echo if root not in hits),
        "requests_with_leak": requests_with_leak,
    }
