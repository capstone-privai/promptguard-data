"""The HTTP server hands out the UI and result files only, behind optional Basic authentication."""

from __future__ import annotations

import base64
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import serve  # noqa: E402

KEY = "0123456789abcdef"


class QuietHandler(serve.Handler):
    def log_message(self, format, *args):  # noqa: A002 - the 404s here are expected
        pass


class ServeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        (data / "index.json").write_text("{}", encoding="utf-8")
        (data / "failures.json").write_text("{}", encoding="utf-8")
        (data / "repo.git").mkdir()
        (data / "repo.git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        result = data / "results" / "detection" / KEY
        (result / "examples").mkdir(parents=True)
        (result / "summary.json").write_text("{}", encoding="utf-8")
        (result / "meta.json").write_text("{}", encoding="utf-8")
        (result / "examples" / "sessions_2.json").write_text("{}", encoding="utf-8")
        self.auth = "Basic " + base64.b64encode(b"team:pw").decode()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, service=None, data_dir=data,
                                                                    auth=self.auth))
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def status(self, path, auth=True, method="GET"):
        request = urllib.request.Request(self.base + path, method=method,
                                         headers={"Authorization": self.auth} if auth else {})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code

    def test_result_files_and_ui_are_served(self):
        for path in ("/", "/app.js", "/style.css", "/data/index.json", f"/data/results/detection/{KEY}/summary.json",
                     f"/data/results/detection/{KEY}/examples/sessions_2.json", "/api/status"):
            self.assertEqual(self.status(path), 200, path)

    def test_everything_else_is_not(self):
        for path in ("/data/failures.json", "/data/repo.git/HEAD", f"/data/results/detection/{KEY}/meta.json",
                     "/data/results/detection/../../index.json", "/data/results/detection/zz/summary.json",
                     f"/data/results/detection/{KEY}/examples/../summary.json", "/serve.py", "/../serve.py"):
            self.assertEqual(self.status(path), 404, path)

    def test_basic_auth_guards_every_route(self):
        self.assertEqual(self.status("/", auth=False), 401)
        self.assertEqual(self.status("/data/index.json", auth=False), 401)
        self.assertEqual(self.status("/api/refresh", method="POST", auth=False), 401)

    def test_refresh_needs_a_service(self):
        self.assertEqual(self.status("/api/refresh", method="POST"), 404)


if __name__ == "__main__":
    unittest.main()
