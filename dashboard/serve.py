"""PromptGuard evaluation dashboard: keep the PromptGuard branch evaluated and serve the web UI.

Run from anywhere (paths are relative to this repository):
  python dashboard/serve.py                 # poll the branch, evaluate new commits, serve http://127.0.0.1:8765
  python dashboard/serve.py --once          # evaluate whatever is missing, then exit (for cron)
  python dashboard/serve.py --serve-only    # serve what the data directory already holds
  python dashboard/serve.py --export DIR    # write a static copy of the UI and its data to DIR, then exit

The data directory holds dataset text, secrets included (example windows). Serve it to your team only; --auth
puts HTTP Basic authentication in front of every route. See dashboard/README.md.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hmac
import json
import os
import re
import shutil
import signal
import sys
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.paths import DEFAULT_DATA_DIR, WEB_ROOT  # noqa: E402
from pipeline.runner import tool_version  # noqa: E402
from pipeline.service import Config, DataDirBusy, Service  # noqa: E402

DEFAULT_REPO = "https://github.com/capstone-privai/promptguard-claude-demoV0.git"
RESTART = 75  # exit status when the code changed on disk: run again to load it (systemd Restart=on-failure)
BUSY = 3  # --once exit status when another process evaluates in the data directory: nothing was done
STATIC = re.compile(r"[A-Za-z0-9_-]+\.(?:js|css|svg|png|ico)")
DATA = re.compile(r"index\.json|results/(?:detection|latency|task)/[0-9a-f]{16}/"
                  r"(?:summary\.json|latency\.json|task\.json|examples/[A-Za-z0-9_-][A-Za-z0-9_.-]*\.json)")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    server_version = "promptguard-dashboard"

    def __init__(self, *args, service: Service | None, data_dir: Path, auth: str | None, **kwargs):
        self.service, self.data_dir, self.auth = service, data_dir, auth
        super().__init__(*args, **kwargs)

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        if str(code).startswith(("4", "5")):  # successful requests stay out of the log
            super().log_request(code, size)

    def _authorized(self) -> bool:
        if not self.auth:
            return True
        header = self.headers.get("Authorization", "")
        if hmac.compare_digest(header.encode(), self.auth.encode()):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="PromptGuard dashboard", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-cache") -> None:
        if len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "") and not content_type.startswith("image/"):
            body = gzip.compress(body, compresslevel=6)
            encoded = True
        else:
            encoded = False
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        if encoded:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path: Path, cache: str = "no-cache") -> None:
        try:
            body = path.read_bytes()
        except OSError:
            return self._send(404, b"not found", "text/plain; charset=utf-8")
        self._send(200, body, TYPES.get(path.suffix, "application/octet-stream"), cache)

    def _json(self, status: int, value: object) -> None:
        self._send(status, json.dumps(value, ensure_ascii=False).encode(), TYPES[".json"])

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = urlsplit(self.path).path
        if path == "/api/status":
            status = self.service.snapshot() if self.service else {"state": "serve-only"}
            return self._json(200, status)
        if path in ("/", "/index.html"):
            return self._file(WEB_ROOT / "index.html")
        if path.startswith("/data/") and DATA.fullmatch(path[len("/data/"):]):
            relative = path[len("/data/"):]
            return self._file(self.data_dir / relative, "no-cache" if relative == "index.json" else "max-age=3600")
        if STATIC.fullmatch(path.lstrip("/")):
            return self._file(WEB_ROOT / path.lstrip("/"), "no-cache")
        self._send(404, b"not found", "text/plain; charset=utf-8")

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        parts = urlsplit(self.path)
        if parts.path == "/api/refresh" and self.service:
            retry = parse_qs(parts.query).get("retry") == ["1"]
            self.service.request_refresh(retry=retry)
            return self._json(202, {"ok": True, "retry": retry})
        self._send(404, b"not found", "text/plain; charset=utf-8")


def export(data_dir: Path, out: Path) -> None:
    """The UI plus index.json and every result file it can load, as plain files for any static web server."""
    out.mkdir(parents=True, exist_ok=True)
    for path in WEB_ROOT.iterdir():
        if path.name == "index.html" or STATIC.fullmatch(path.name):
            shutil.copy2(path, out / path.name)
    for path in sorted(data_dir.rglob("*.json")):
        relative = path.relative_to(data_dir).as_posix()
        if DATA.fullmatch(relative):
            target = out / "data" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    print(f"static copy: {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PromptGuard evaluation dashboard (see dashboard/README.md)")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1; 0.0.0.0 for "
                                                            "every interface)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help=f"default {DEFAULT_DATA_DIR}")
    parser.add_argument("--repo", default=os.environ.get("PROMPTGUARD_REPO", DEFAULT_REPO),
                        help="PromptGuard repository to clone (URL or path; default $PROMPTGUARD_REPO, else the "
                             "GitHub repository)")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--poll-minutes", type=float, default=10.0, help="how often to fetch the branch (default 10)")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1),
                        help="detection shards run side by side (default: CPUs - 1)")
    parser.add_argument("--python", default=sys.executable,
                        help="Python for the evaluators; needs the CredSweeper version the commit pins, else a "
                             "virtual environment is made per requirements.txt (default: this Python)")
    parser.add_argument("--no-auto-venv", action="store_true", help="fail instead of making a virtual environment")
    parser.add_argument("--no-latency", action="store_true", help="skip metric-latency")
    parser.add_argument("--latency-adapters", choices=("ensemble", "each"), default="each",
                        help="also time each detector adapter alone (default each)")
    parser.add_argument("--latency-guard", nargs="+", default=[], metavar="PATH",
                        help="metric-task run folders whose API captures to replay as Final Guard calls")
    parser.add_argument("--task-runs", nargs="+", metavar="DIR", default=None,
                        help="folders holding metric-task batch folders (batch.json + runs.csv) to show; never run "
                             "by the dashboard (default runs/metric-task)")
    parser.add_argument("--no-task", action="store_true", help="hide metric-task")
    parser.add_argument("--auth", default=os.environ.get("DASHBOARD_AUTH"),
                        help="USER:PASSWORD for HTTP Basic authentication (default $DASHBOARD_AUTH)")
    parser.add_argument("--notify-url", default=os.environ.get("DASHBOARD_NOTIFY_URL"),
                        help="Discord webhook for failure alerts (default $DASHBOARD_NOTIFY_URL; prefer the variable, "
                             "the URL is a secret)")
    parser.add_argument("--dashboard-url", default=os.environ.get("DASHBOARD_URL"),
                        help="link put under each alert (default $DASHBOARD_URL)")
    parser.add_argument("--overdue-hours", type=float, default=24.0,
                        help="alert once when a job runs this long (default 24; 0 never)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="evaluate what is missing, then exit")
    mode.add_argument("--serve-only", action="store_true", help="serve without fetching or evaluating")
    mode.add_argument("--export", metavar="DIR", help="write a static copy of the UI and data, then exit")
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    if args.export:
        export(data_dir, Path(args.export))
        return 0

    service = None
    if not args.serve_only:
        if tool_version(["gitleaks", "version"]) is None:
            print("warning: gitleaks is not on PATH; the detector will run without its gitleaks adapter, unlike "
                  "the deployed system", file=sys.stderr)
        config = Config(data_dir=data_dir, repo_url=args.repo, branch=args.branch, jobs=args.jobs,
                        python=args.python, auto_venv=not args.no_auto_venv, latency=not args.no_latency,
                        latency_adapters=args.latency_adapters, latency_guard=args.latency_guard,
                        task=not args.no_task, notify_url=args.notify_url, dashboard_url=args.dashboard_url,
                        overdue_hours=args.overdue_hours)
        if args.task_runs:
            config.task_runs = args.task_runs
        service = Service(config)
        if args.once:
            signal.signal(signal.SIGTERM, lambda *_args: service.stop())  # stop the running job, record no failure
            try:
                service.run_until_done()
            except DataDirBusy as busy:
                print(f"{busy} ({data_dir}); did nothing", file=sys.stderr)
                return BUSY
            return RESTART if service.code_changed else 0

    auth = "Basic " + base64.b64encode(args.auth.encode()).decode() if args.auth else None
    if args.host not in ("127.0.0.1", "localhost", "::1") and not auth:
        print("warning: serving dataset text without --auth on a non-loopback address", file=sys.stderr)
    server = ThreadingHTTPServer((args.host, args.port),
                                 partial(Handler, service=service, data_dir=data_dir, auth=auth))
    worker = None
    if service:
        def work() -> None:
            service.run_forever(args.poll_minutes * 60)
            if service.code_changed:
                server.shutdown()

        worker = threading.Thread(target=work, daemon=True)
        worker.start()

    def shutdown(*_args) -> None:
        if service:
            service.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    print(f"dashboard: http://{args.host}:{args.port}/  (data: {data_dir})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        shutdown()
    finally:
        if worker:
            worker.join(timeout=30)
        server.server_close()
    return RESTART if service and service.code_changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
