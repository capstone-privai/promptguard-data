"""Records what the PromptGuard mod sends to its detector during one metric 2 run.

The runner puts this proxy between the mod's MCP bridge and the detector worker (the bridge's
PG_MOD_DETECTOR_URL points here) and it relays every request unchanged. For each POST it keeps the request
items (id, text, source), the HTTP status, how long the worker took as seen from here, the worker's own
latency_ms and the finding count per item. Metric 4 replays these calls (m4.py run --recorded) to time a
detector on exactly the text the mod handed it.

The file holds the task's secrets as the mod saw them, like api_requests.jsonl.xz: it stays in the run folder.

  DetectorCapture(out_path, upstream_url).start() -> url;  .stop() writes detector_calls.jsonl.xz
"""
from __future__ import annotations

import http.client
import json
import lzma
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

CAPTURE_FILE = "detector_calls.jsonl.xz"


class DetectorCapture:
    def __init__(self, out_path: Path, upstream: str):
        self.out_path = Path(out_path)
        self.upstream = urlsplit(upstream.rstrip("/"))
        self.records: list[dict] = []
        self.lock = threading.Lock()
        self.arrivals = 0
        self.server: ThreadingHTTPServer | None = None

    def start(self) -> str:
        capture = self

        class Handler(_Handler):
            owner = capture

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def arrive(self) -> int:
        with self.lock:
            self.arrivals += 1
            return self.arrivals - 1

    def add(self, record: dict):
        with self.lock:
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
            for r in sorted(records, key=lambda r: r["seq"]):
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return len(records)


class _Handler(BaseHTTPRequestHandler):
    owner: DetectorCapture

    def log_message(self, _format, *_args):
        return

    def relay(self):
        body = self.rfile.read(int(self.headers.get("content-length") or 0))
        # seq is the order requests arrived in, which is the order the mod sent them (its calls are serialized).
        record = {"seq": self.owner.arrive(), "t": round(time.time(), 3), "method": self.command, "path": self.path,
                  "status": None}
        if self.command == "POST":
            try:
                record["items"] = json.loads(body).get("items")
            except (ValueError, AttributeError):
                record["items"] = None
        conn = http.client.HTTPConnection(self.owner.upstream.hostname, self.owner.upstream.port, timeout=120)
        try:
            headers = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "content-length")}
            started = time.perf_counter()
            conn.request(self.command, self.path, body=body or None, headers=headers)
            response = conn.getresponse()
            data = response.read()
            record["upstream_ms"] = round((time.perf_counter() - started) * 1000, 3)
            record["status"] = response.status
            try:
                items = json.loads(data).get("items") or []
                latencies = [i.get("latency_ms") for i in items if isinstance(i.get("latency_ms"), (int, float))]
                record["latency_ms"] = max(latencies) if latencies else None
                record["finding_counts"] = [len(i.get("findings") or []) for i in items]
            except (ValueError, AttributeError):
                pass
            self.send_response(response.status)
            for k, v in response.getheaders():
                if k.lower() in ("content-type", "content-length"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # worker unreachable: the bridge sees a 502, as it would without this proxy
            record["error"] = f"{type(e).__name__}: {e}"[:300]
            if record["status"] is None:
                self.send_response(502)
                self.send_header("content-length", "0")
                self.end_headers()
        finally:
            conn.close()
            if self.command == "POST":
                self.owner.add(record)

    do_GET = do_POST = relay
