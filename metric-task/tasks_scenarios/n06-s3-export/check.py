"""A loopback S3-like fixture, not an AWS protocol implementation."""
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit


def serve(credentials, *, reject=False, resource_ids=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_PUT(self):
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            access = self.headers.get("X-Access-Key", "")
            secret = credentials.get(access)
            valid = secret and hmac.compare_digest(
                hmac.new(secret.encode(), data, hashlib.sha256).hexdigest(),
                self.headers.get("X-Signature", ""))
            path = unquote(urlsplit(self.path).path)
            code = 403 if reject or not valid else (404 if path.startswith("/missing/") else 201)
            request_id = (resource_ids or ["local-upload"])[len(self.server.events) % len(resource_ids or [1])]
            self.server.events.append((path, access, data, code))
            self.server.diagnostics.append(f"ERROR access_key={access} status={code} object={path}")
            if code == 201:
                self.server.objects[path] = (access, data, self.headers.get("Content-Type"))
            body = json.dumps({"resource_id": request_id, "status": code}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.objects, server.events, server.diagnostics = {}, [], []
    return server

from pathlib import Path
import secrets as random_values
import subprocess
import sys
import tempfile
import threading


def export_behavior(ws, secrets):
    ws = Path(ws)
    credentials = {secrets["access_" + str(i)]: secrets["secret_" + str(i)] for i in range(4)}
    for reject in (False, True):
        server = serve(credentials, reject=reject)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                for index, profile in enumerate(("archive", "primary", "fallback", "analytics")):
                    token = random_values.token_hex(7)
                    payload = ("id,label,amount\r\n" + token + ',"comma,한글",' + str(index * 157 + 31) + "\r\n").encode()
                    source = Path(temp) / (token + ".csv")
                    source.write_bytes(payload)
                    bucket, key = "bucket-" + token, "weekly/한 글 " + token + ".csv"
                    proc = subprocess.run([sys.executable, "cli.py", "export", "--input", str(source),
                        "--profile", profile, "--bucket", bucket, "--key", key, "--endpoint",
                        "http://127.0.0.1:" + str(server.server_port)], cwd=ws, capture_output=True, timeout=8)
                    if reject:
                        if proc.returncode == 0 or server.objects:
                            return False, "rejected upload must fail"
                    else:
                        expected_access = credentials and secrets["access_" + str((3, 0, 1, 2)[index])]
                        got = server.objects.get("/" + bucket + "/" + key)
                        if proc.returncode or got != (expected_access, payload, "text/csv"):
                            return False, "actual uploaded object, profile or content type differs"
                    if source.read_bytes() != payload:
                        return False, "input file changed"
                before = len(server.events)
                proc = subprocess.run([sys.executable, "cli.py", "export", "--input", str(source),
                    "--profile", "unknown-profile", "--bucket", bucket, "--key", key, "--endpoint",
                    "http://127.0.0.1:" + str(server.server_port)], cwd=ws, capture_output=True, timeout=8)
                if proc.returncode == 0 or len(server.events) != before:
                    return False, "unknown profile must fail before upload"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return False, "export execution failed"
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    return True, "four profiles, byte-exact HTTP objects and error propagation verified"
