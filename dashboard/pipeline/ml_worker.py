"""Timed HTTP endpoint for detector → JSONL KEEP/MASK, used through m4's cmd: protocol.

The batch timer starts before parsing the input and ends after all final decisions. Model IPC and
inference are inside that interval; process startup is recorded separately. No detection cache is used.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.ml import inference, load_spec
from evaluation.adapters.promptguard_adapter import CHANNEL_MAP, PromptGuardAdapter
from evaluation.adapters.system_root import load_worker
from evaluation.adapters.two_stage_adapter import classify_findings
from evaluation.adapters.span_union_adapter import SpanUnionAdapter


def make_handler(adapter, classifier):
    lock = threading.Lock()
    channel_of = {source: channel for channel, source in CHANNEL_MAP.items()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def send_json(self, status, value):
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path not in ("/health", "/status", "/ready"):
                return self.send_json(404, {"ok": False})
            self.send_json(200, {"ok": True, "pipeline": ("detector-span-union" if getattr(classifier, "mode", "candidate") == "span_union"
                                                          else "detector-ml"), "second_stage": classifier.describe(),
                                 **adapter.detector.describe()})

        def do_POST(self):
            if self.path != "/scan-batch":
                return self.send_json(404, {"ok": False})
            started = time.perf_counter()
            try:
                payload = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
                items = payload["items"]
                if (not isinstance(items, list) or not all(isinstance(item, dict)
                        and isinstance(item.get("text"), str) for item in items)):
                    raise ValueError("invalid input batch")
            except (ValueError, KeyError, TypeError):
                return self.send_json(400, {"ok": False, "error": "INVALID_BATCH"})
            try:
                results = []
                with lock:
                    for index, item in enumerate(items):
                        source = item.get("source", "tool_result")
                        context = {"session_id": str(payload.get("request_id", "latency")), "item_id": index,
                                   "turn_id": 0, "channel": channel_of.get(source, "tool_output")}
                        if getattr(classifier, "mode", "candidate") == "span_union":
                            result = adapter.scan_union(item["text"], source, **context)
                        else:
                            result, _ = classify_findings(classifier, item["text"],
                                                          adapter._scan(item["text"], source), **context)
                        results.append({**result, "id": item.get("id"), "finding_count": len(result["findings"])})
                elapsed = (time.perf_counter() - started) * 1000
                for result in results:
                    result["latency_ms"] = elapsed
                self.send_json(200, {"ok": True, "request_id": payload.get("request_id"), "items": results})
            except Exception as exc:
                # No raw text, candidate values or command output in errors. Never fall back to rule-only.
                self.send_json(500, {"ok": False, "error": type(exc).__name__})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--system-root", required=True)
    parser.add_argument("--ml-config", required=True)
    args = parser.parse_args()
    spec = load_spec(args.ml_config)
    classifier = inference(spec)
    server = None
    def stop(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        worker = load_worker(args.system_root)
        adapter = SpanUnionAdapter(classifier, worker) if spec.mode == "span_union" else PromptGuardAdapter(worker)
        server = ThreadingHTTPServer(("127.0.0.1", int(os.environ["PG_DETECTOR_PORT"])),
                                     make_handler(adapter, classifier))
        server.daemon_threads = True
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        classifier.close()


if __name__ == "__main__":
    main()
