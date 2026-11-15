"""Serve the checked-in recordings at an ephemeral loopback endpoint."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading


def replay():
    entries = []
    for path in sorted(Path('tests/recordings').glob('*.har')):
        entries.extend(json.loads(path.read_text())['log']['entries'])
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            entry = next((e for e in entries if e['request']['url'].split('local.invalid')[-1] == self.path), None)
            if entry is None:
                self.send_error(404)
                return
            response = entry['response']
            self.send_response(response['status'])
            self.send_header('Content-Type', 'application/json')
            for header in response['headers']:
                self.send_header(header['name'], header['value'])
            self.end_headers()
            self.wfile.write(response['content']['text'].encode())
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        for entry in entries:
            request = entry['request']
            args = ['curl', '--noproxy', '*', '--max-time', '5', '-v']
            for header in request['headers']:
                args.extend(['-H', header['name'] + ': ' + header['value']])
            args.append('http://127.0.0.1:' + str(server.server_port) + request['url'].split('local.invalid')[-1])
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            print(result.stderr + result.stdout, flush=True)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()

if __name__ == '__main__':
    replay()
