"""Live demo view of the PromptGuard Native Mod pipeline: channel and input -> the spans each detector module
flagged -> their union, the masked spans -> the text the Mod forwards to the model.

The Mod in promptguard-claude-demoV0 (src/native-mod) sends every text bound for the model to its detector over
HTTP (POST /scan-batch, through its MCP bridge). This script takes the detector's place: it loads the checkout's
own ensemble (src/detector/pgdetector with its detector.json) and answers the Mod exactly as src/detector/worker.py
would, while keeping every adapter's spans. It masks by detector.json's own rule, as the plugin does: under
candidate_policy "union" (shipped) every module's spans are unioned, under "majority" only regions enough voting
modules agree on; --policy and --consensus override it. It then replays the Mod's placeholder rules on the answer
to rebuild the text the Mod forwards, and pushes each step to the browser.

  python3 demo/pipeline_demo.py play                 # a copy of the sample project + Claude Code with the Mod, opens the page
  python3 demo/pipeline_demo.py play --project DIR   # in DIR instead
  python3 demo/pipeline_demo.py serve                # detector + page only; point a Mod's bridge at it

Open http://127.0.0.1:18790. The page shows raw secret values: it listens on 127.0.0.1 only, so use synthetic
secrets. The script re-runs itself with the checkout's .venv Python, which has the detector's dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEB_ROOT = HERE / "web"
REPO_ROOT = HERE.parent
HOST = "127.0.0.1"
DEFAULT_PORT = 18790
MAX_BODY = 8 * 1024 * 1024
KEEP_EVENTS = 300
PREVIEW_CHARS = 2000  # texts with nothing flagged are cut to this for the page
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
# Same as metric-task's m2.py: without this permission the Mod's call to its detector is refused, the hook is
# skipped and the text reaches the model unmasked.
ALLOWED_TOOLS = "mcp__pgdetector__scan_batch"
# Set when this script runs inside another Claude Code session; a child session must not inherit them.
PARENT_SESSION_ENV = ("CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_MESSAGING_SOCKET",
                      "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_CHILD_SESSION",
                      "CLAUDE_CODE_SESSION_ATTENDED", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION",
                      "CLAUDE_CODE_EXECPATH", "CLAUDE_CODE_ENABLE_SDK_FILE_CHECKPOINTING",
                      "CLAUDE_CODE_EMIT_STARTUP_TIMING", "CLAUDE_CODE_QUESTION_PREVIEW_FORMAT", "PG_MOD_FAILURE_MODE")


def system_root(arg: str | None) -> Path:
    root = Path(arg or os.environ.get("PROMPTGUARD_CLAUDE_ROOT") or REPO_ROOT.parent / "promptguard-claude-demoV0")
    for required in (("native-mod", "hooks", "register.mjs"), ("detector", "pgdetector", "ensemble.py"),
                     ("detector", "mcp-bridge.cjs")):
        if not (root / "src" / Path(*required)).is_file():
            raise SystemExit(f"no src/{'/'.join(required)} under {root}; pass --system-root or set "
                             "PROMPTGUARD_CLAUDE_ROOT to a promptguard-claude-demoV0 checkout")
    return root.resolve()


def use_system_python(pg_root: Path) -> None:
    """Re-runs this script with the checkout's .venv Python unless it already is that Python."""
    venv = pg_root / ".venv"
    if Path(sys.prefix).resolve() == venv.resolve():
        return
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise SystemExit(f"{python} missing; run install.sh in {pg_root} first")
    os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])


# ---- the Mod's placeholder rules -----------------------------------------------------------------------------

def type_name(value) -> str:
    """register.mjs typeName()."""
    name = "".join(c if c.isascii() and c.isalnum() or c == "_" else "_" for c in str(value or "CREDENTIAL").upper())
    return name or "CREDENTIAL"


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def utf16_slice(text: str, start: int, end: int) -> str:
    return text.encode("utf-16-le")[2 * start:2 * end].decode("utf-16-le")


def utf16_table(text: str) -> list[int] | None:
    """Code point index -> UTF-16 offset, or None when the two agree (no characters outside the BMP)."""
    if all(ord(c) < 0x10000 for c in text):
        return None
    table = [0]
    for c in text:
        table.append(table[-1] + (2 if ord(c) > 0xFFFF else 1))
    return table


class ModReplica:
    """The Mod's placeholder ledger and re-masking (register.mjs placeholder, redactText, remaskText), replayed on
    the detector's answers. Like the Mod's, it lives as long as one Claude Code session."""

    def __init__(self) -> None:
        self.ledger: dict[str, str] = {}
        self.counters: dict[str, int] = {}
        self.reverse: dict[str, str] = {}  # raw value -> placeholder, the Mod's reverseVault

    def placeholder(self, finding: dict, raw: str) -> str:
        kind = type_name(finding.get("type"))
        key = f"{kind}:{finding.get('value_hash')}"
        if key in self.ledger:
            return self.ledger[key]
        self.counters[kind] = self.counters.get(kind, 0) + 1
        value = f"[{kind}_{self.counters[kind]}]"
        self.ledger[key] = value
        self.reverse.setdefault(raw, value)
        return value

    def redact(self, text: str, findings: list[dict]) -> list:
        """Segments of the redacted text: (plain text, its UTF-16 offset in the input) and {mask, raw, how: "vote",
        start, end}. Placeholders are handed out from the end of the text backwards, as redactText() does, so
        numbering matches the Mod's."""
        cuts = []
        for finding in sorted(findings, key=lambda f: (-f["start"], -f["end"])):
            raw = utf16_slice(text, finding["start"], finding["end"])
            cuts.append((finding["start"], finding["end"], self.placeholder(finding, raw), raw))
        segments, cursor = [], 0
        for start, end, mask, raw in reversed(cuts):
            segments += [(utf16_slice(text, cursor, start), cursor),
                         {"mask": mask, "raw": raw, "how": "vote", "start": start, "end": end}]
            cursor = end
        segments.append((utf16_slice(text, cursor, utf16_len(text)), cursor))
        return [s for s in segments if not isinstance(s, tuple) or s[0]]

    def remask(self, segments: list) -> list:
        """remaskText(): raw values the Mod already holds are replaced wherever they appear, longest first, even
        when no detector flagged them this time (how: "remask")."""
        for raw in sorted(self.reverse, key=len, reverse=True):
            out = []
            for segment in segments:
                if not isinstance(segment, tuple) or raw not in segment[0]:
                    out.append(segment)
                    continue
                at = segment[1]
                for index, part in enumerate(segment[0].split(raw)):
                    if index:
                        out.append({"mask": self.reverse[raw], "raw": raw, "how": "remask",
                                    "start": at, "end": at + utf16_len(raw)})
                        at += utf16_len(raw)
                    if part:
                        out.append((part, at))
                    at += utf16_len(part)
            segments = out
        return [s[0] if isinstance(s, tuple) else s for s in segments]


# ---- the detector stand-in -----------------------------------------------------------------------------------

def regions(text: str, ballots: dict, findings: list[dict], adapters: list[str]) -> list[dict]:
    """Every adapter's findings grouped into regions of overlapping spans (the vote counts any overlap as
    agreeing), each with who voted for it, whether it was masked and the masked spans inside it (the union of the
    accepted findings, after normalize()). Offsets are UTF-16, as in the browser."""
    table = utf16_table(text)
    to16 = (lambda i: i) if table is None else (lambda i: table[i])
    # Out-of-range ballots never reach the vote (Detector.accept drops them), so they are not shown either.
    flat = sorted(((name, f) for name in adapters for f in ballots.get(name, []) if 0 <= f.start < f.end <= len(text)),
                  key=lambda x: (x[1].start, x[1].end))
    groups: list[dict] = []
    for name, f in flat:
        if not groups or f.start >= groups[-1]["_end"]:
            groups.append({"_end": f.end, "start": f.start, "votes": []})
        group = groups[-1]
        group["_end"] = max(group["_end"], f.end)
        group["votes"].append({"adapter": name, "type": f.type, "rule": f.rule_id,
                               "start": to16(f.start), "end": to16(f.end)})
    out = []
    for group in groups:
        start, end = to16(group["start"]), to16(group["_end"])
        final = [{"start": s, "end": e} for s, e in sorted({(f["start"], f["end"]) for f in findings
                                                            if f["start"] < end and start < f["end"]})]
        out.append({"start": start, "end": end, "votes": group["votes"],
                    "voters": sorted({v["adapter"] for v in group["votes"]}, key=adapters.index),
                    "masked": bool(final), "final": final})
    return out


class Tap:
    """Serves the checkout's ensemble to the Mod and records each batch for the page."""

    def __init__(self, detector) -> None:
        self.detector = detector
        self.local = threading.local()
        collect = detector.collect

        def collect_and_keep(texts):
            per_text, errors = collect(texts)
            self.local.ballots = per_text
            return per_text, errors

        # scan_many() itself stays the checkout's, so the Mod gets exactly the worker's answer.
        detector.collect = collect_and_keep
        self.mod = ModReplica()
        self.lock = threading.Lock()
        self.events: deque = deque(maxlen=KEEP_EVENTS)
        self.listeners: set[queue.Queue] = set()
        self.seq = 0
        self.boot = secrets.token_hex(4)  # lets a reconnecting page tell a restarted server from a dropped stream

    def describe(self) -> dict:
        info = self.detector.describe()
        adapters = [a["name"] for a in info["adapters"]]
        # protection_adapters: whose spans can get a value masked. Under "majority" candidate-only modules
        # (shell-aware) still scan but do not vote. Checkouts without candidate_policy vote with every module.
        return {"boot": self.boot, "policy": info.get("candidate_policy", "majority"), "consensus": info["consensus"],
                "required": info["required_votes"], "adapters": adapters,
                "voters": info.get("protection_adapters", adapters), "skipped": [s["name"] for s in info["skipped"]]}

    def scan_many(self, items: list[tuple[str, str]]) -> list[dict]:
        self.local.ballots = None
        results = self.detector.scan_many(items)
        try:
            self.record(items, results, self.local.ballots or [{} for _ in items])
        except Exception as exc:  # the page is a bystander: never fail the Mod's scan over it
            print(f"pipeline demo: could not record a scan ({type(exc).__name__}: {exc})", file=sys.stderr, flush=True)
        return results

    def record(self, items, results, ballots) -> None:
        adapters = self.detector.names
        # The Mod rejects the whole batch when any item is not clean (scanBatch), before handing out placeholders.
        ok = all(r.get("ok") is True and not r.get("errors") for r in results)
        with self.lock:
            redacted = [self.mod.redact(text, r["findings"]) if ok else [text] for (text, _), r in zip(items, results)]
            forwarded = [self.mod.remask(segments) for segments in redacted] if ok else redacted
            shown = []
            for (text, _), result, ballot, segments in zip(items, results, ballots, forwarded):
                if not text.strip():
                    continue
                found = regions(text, ballot, result.get("findings", []), adapters)
                changed = segments != [text]
                quiet = not found and not changed and not result.get("errors")
                shown.append({"text": text[:PREVIEW_CHARS] if quiet else text, "length": len(text),
                              "regions": found, "output": None if quiet else segments,
                              "errors": result.get("errors") or []})
            if not shown:
                return
            self.seq += 1
            event = {"seq": self.seq, "time": time.time(), "source": items[0][1], "ok": ok, "items": shown,
                     "latency_ms": results[0].get("latency_ms") if results else None}
            self.events.append(event)
            for listener in list(self.listeners):
                listener.put(event)

    def listen(self) -> tuple[queue.Queue, list[dict]]:
        listener: queue.Queue = queue.Queue()
        with self.lock:
            self.listeners.add(listener)
            return listener, list(self.events)

    def unlisten(self, listener: queue.Queue) -> None:
        with self.lock:
            self.listeners.discard(listener)


class Handler(BaseHTTPRequestHandler):
    """The worker's detector protocol for the Mod, plus the page and its event stream."""

    server_version = "PromptGuardPipelineDemo/0.1"
    tap: Tap
    port: int

    def log_message(self, _format, *_args) -> None:
        return

    def send_json(self, status: int, value) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local_host(self) -> bool:
        # The page carries raw secrets: refuse names other than loopback (DNS rebinding).
        return self.headers.get("host", "") in {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in {"/health", "/ready", "/status"}:
            self.send_json(200, {"ok": True, "ready": True, "role": "pipeline-demo", **self.tap.detector.describe()})
            return
        if not self.local_host():
            self.send_json(403, {"ok": False, "error": "HOST"})
            return
        if path == "/events":
            self.stream()
            return
        if path not in STATIC:
            self.send_json(404, {"ok": False, "error": "NOT_FOUND"})
            return
        name, kind = STATIC[path]
        body = (WEB_ROOT / name).read_bytes()
        self.send_response(200)
        self.send_header("content-type", kind)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def stream(self) -> None:
        listener, backlog = self.tap.listen()
        try:
            self.send_response(200)
            self.send_header("content-type", "text/event-stream; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.end_headers()
            self.emit("setup", self.tap.describe())
            for event in backlog:
                self.emit("scan", event)
            self.emit("live", {})  # from here on, scans happen as the page watches
            while True:
                try:
                    self.emit("scan", listener.get(timeout=15))
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.tap.unlisten(listener)

    def emit(self, name: str, value) -> None:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        self.wfile.write(f"event: {name}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()

    def do_POST(self) -> None:
        if self.path not in {"/scan", "/scan-batch"}:
            self.send_json(404, {"ok": False, "error": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            if length <= 0 or length > MAX_BODY:
                self.send_json(413, {"ok": False, "error": "BODY_SIZE"})
                return
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            request_id = payload.get("request_id") if isinstance(payload.get("request_id"), str) else None
            if self.path == "/scan":
                text, source = payload.get("text"), payload.get("source", "unknown")
                if not isinstance(text, str) or not isinstance(source, str):
                    self.send_json(400, {"ok": False, "error": "INVALID_INPUT"})
                    return
                self.send_json(200, {"request_id": request_id, **self.tap.scan_many([(text, source)])[0]})
                return
            items = payload.get("items")
            if not isinstance(items, list) or len(items) > 4096:
                self.send_json(400, {"ok": False, "error": "INVALID_BATCH"})
                return
            if not all(isinstance(item, dict) and isinstance(item.get("text"), str) for item in items):
                self.send_json(400, {"ok": False, "error": "INVALID_ITEM"})
                return
            results = self.tap.scan_many([(item["text"], str(item.get("source", "unknown"))) for item in items])
            output = [{"id": item.get("id"), **result} for item, result in zip(items, results)]
            self.send_json(200, {"ok": all(item.get("ok") for item in output), "request_id": request_id,
                                 "items": output})
        except Exception:
            self.send_json(500, {"ok": False, "error": "DETECTOR_EXCEPTION"})


def start_server(pg_root: Path, port: int, consensus: str | None, policy: str | None) -> tuple[ThreadingHTTPServer, Tap]:
    sys.path.insert(0, str(pg_root / "src" / "detector"))
    from pgdetector import load_detector

    if policy:
        os.environ["PG_DETECTOR_CANDIDATE_POLICY"] = policy  # load_detector() reads it over detector.json's
    tap = Tap(load_detector(consensus=consensus))
    handler = type("BoundHandler", (Handler,), {"tap": tap, "port": port})
    server = ThreadingHTTPServer((HOST, port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    info = tap.describe()
    rule = "union" if info["policy"] == "union" else f"majority vote: consensus {info['consensus']}"
    print(f"detectors: {', '.join(info['adapters'])} ({rule}, {info['required']} vote(s) to mask)"
          + (f"; skipped: {', '.join(info['skipped'])}" if info["skipped"] else ""))
    print(f"page:      http://{HOST}:{port}")
    return server, tap


# ---- commands ------------------------------------------------------------------------------------------------

def cmd_serve(args, pg_root: Path) -> None:
    server, _ = start_server(pg_root, args.port, args.consensus, args.policy)
    print(f"detector:  point the Mod's bridge here with PG_MOD_DETECTOR_URL=http://{HOST}:{args.port}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


def cmd_play(args, pg_root: Path) -> None:
    server, _ = start_server(pg_root, args.port, args.consensus, args.policy)
    url = f"http://{HOST}:{args.port}"
    work = Path(tempfile.mkdtemp(prefix="pg-pipeline-demo-"))
    if args.project:
        project = Path(args.project).resolve()
    else:
        # A copy, so whatever Claude edits stays out of the checkout.
        project = work / "sample-protected-project"
        shutil.copytree(pg_root / "sample-protected-project", project)
    mcp = work / "mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"pgdetector": {
        "command": "node", "args": [str(pg_root / "src" / "detector" / "mcp-bridge.cjs")],
        # The bridge reads PG_MOD_DETECTOR_URL first; set both so an inherited value cannot win.
        "env": {"PG_MOD_DETECTOR_URL": url, "PG_DETECTOR_URL": url}}}}), encoding="utf-8")
    argv = ["claude", "--plugin-dir", str(pg_root / "src" / "native-mod"), "--mcp-config", str(mcp),
            "--strict-mcp-config", "--allowedTools", ALLOWED_TOOLS, *args.claude_args]
    env = {k: v for k, v in os.environ.items() if k not in PARENT_SESSION_ENV}
    env.update({"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1", "PG_DETECTOR_URL": url,
                "PG_MOD_AUDIT": str(work / "mod-audit.json"), "PG_SESSION_HASH": secrets.token_hex(32)})
    print(f"project:   {project}")
    print(f"started:   {datetime.now():%H:%M:%S}; exit Claude Code (/exit) to stop\n")
    webbrowser.open(url)  # Claude Code takes over the terminal next, so the printed address is easy to miss
    try:
        subprocess.run(argv, cwd=project, env=env)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        shutil.rmtree(work, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("serve", "detector stand-in and page only"),
                            ("play", "also start Claude Code with the Mod attached")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"detector and page port (default {DEFAULT_PORT})")
        p.add_argument("--system-root", help="promptguard-claude-demoV0 checkout (default: ../promptguard-claude-demoV0)")
        p.add_argument("--policy", choices=("union", "majority"),
                       help="mask the union of every module's spans, or only what the vote accepts (default: detector.json's candidate_policy)")
        p.add_argument("--consensus",
                       help="vote rule under --policy majority: any, majority, unanimous or at_least:N (default: detector.json's)")
        if name == "play":
            p.add_argument("--project", help="folder Claude Code works in (default: a copy of sample-protected-project)")
            p.add_argument("claude_args", nargs=argparse.REMAINDER, help="after --: extra arguments for claude")
    args = parser.parse_args()
    pg_root = system_root(args.system_root)
    use_system_python(pg_root)
    if getattr(args, "claude_args", None) and args.claude_args[0] == "--":
        args.claude_args = args.claude_args[1:]
    (cmd_play if args.command == "play" else cmd_serve)(args, pg_root)


if __name__ == "__main__":
    main()
