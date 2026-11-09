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
