"""Stand-in detector for the PromptGuard Claude Code mod, used by the metric 2 conditions none and gold.

The mod in promptguard-claude-demoV0 (src/native-mod) sends every text bound for the model to a local
detector over HTTP (POST /scan-batch, through its MCP bridge) and replaces each finding with a [TYPE_n]
placeholder. This worker speaks the same protocol as src/credsweeper-adapter/worker.py, so the mod runs
unchanged and only what counts as a finding differs:

  --mode none   no findings: the mod runs but masks nothing
  --mode gold   every occurrence of the task's gold secret values, read from --gold
                ({"secrets": [{"name", "type", "value"}, ...]}, one row per surface form)

Gold matching is exact string search, longest value first, without overlaps. It only suits long, unique
values like the generated task secrets; a short value would also match ordinary words.

Standard library only. Listens on 127.0.0.1:$PG_DETECTOR_PORT like the original worker.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "127.0.0.1"
MAX_BODY = 8 * 1024 * 1024
PROCESS_KEY = secrets.token_bytes(32)
MIN_GOLD_LEN = 8


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def value_hash(value: str) -> str:
    # The mod keys its placeholder ledger on this: one value, one placeholder.
    return hmac.new(PROCESS_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()


class Detector:
    def __init__(self, mode: str, gold: list[dict]):
        self.mode = mode
        self.gold = sorted((g for g in gold if len(g["value"]) >= MIN_GOLD_LEN),
                           key=lambda g: -len(g["value"]))

    def scan(self, text: str, source: str) -> dict:
        found: list[tuple[int, int, str]] = []
        if self.mode == "gold":
            taken: list[tuple[int, int]] = []
            for g in self.gold:
                start = text.find(g["value"])
                while start != -1:
                    end = start + len(g["value"])
                    if not any(a < end and start < b for a, b in taken):
                        taken.append((start, end))
                        found.append((start, end, g["type"]))
                    start = text.find(g["value"], start + 1)
        findings = [{
            "type": kind, "rule_id": f"gold:{kind}", "confidence": "strong",
            "value_hash": value_hash(text[start:end]),
            "start": utf16_len(text[:start]), "end": utf16_len(text[:end]),
            "source": source, "offset_unit": "utf16_code_units",
        } for start, end, kind in sorted(found)]
        return {"ok": True, "findings": findings, "errors": [], "finding_count": len(findings),
                "latency_ms": 0, "detector": f"metric2-{self.mode}", "ml": False}


DETECTOR: Detector | None = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        return

    def send_json(self, status: int, value) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/health":
            return self.send_json(404, {"ok": False, "error": "NOT_FOUND"})
        self.send_json(200, {"ok": True, "detector": f"metric2-{DETECTOR.mode}", "ml": False})

    def do_POST(self):
        if self.path not in {"/scan", "/scan-batch"}:
            return self.send_json(404, {"ok": False, "error": "NOT_FOUND"})
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > MAX_BODY:
                return self.send_json(413, {"ok": False, "error": "BODY_SIZE"})
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/scan":
                return self.send_json(200, DETECTOR.scan(payload["text"], str(payload.get("source", "unknown"))))
            items = payload.get("items")
            if not isinstance(items, list):
                return self.send_json(400, {"ok": False, "error": "INVALID_BATCH"})
            out = [{"id": item.get("id"), **DETECTOR.scan(item["text"], str(item.get("source", "unknown")))}
                   for item in items]
            self.send_json(200, {"ok": True, "items": out})
        except Exception:
            self.send_json(500, {"ok": False, "error": "DETECTOR_EXCEPTION"})


def main():
    global DETECTOR
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["none", "gold"], required=True)
    parser.add_argument("--gold", type=Path, help="gold secrets JSON (required with --mode gold)")
    args = parser.parse_args()
    if args.mode == "gold" and not args.gold:
        parser.error("--mode gold needs --gold")
    gold = json.loads(args.gold.read_text(encoding="utf-8"))["secrets"] if args.gold else []
    DETECTOR = Detector(args.mode, gold)
    port = int(os.environ.get("PG_DETECTOR_PORT", "18771"))
    server = ThreadingHTTPServer((HOST, port), Handler)
    print(json.dumps({"ready": True, "host": HOST, "port": port, "mode": args.mode, "gold_values": len(DETECTOR.gold)}),
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
