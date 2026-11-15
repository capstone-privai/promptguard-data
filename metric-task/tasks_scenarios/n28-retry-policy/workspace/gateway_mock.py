"""An offline upstream stub; --serve supplies real loopback HTTP for curl -si."""
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
from urllib.parse import urlsplit
from yaml_subset import load

def resolve(host, path, environment):
    route = next(r for r in sorted(json.loads(Path('gateway/routes.json').read_text()), key=lambda r: -len(r['prefix']))
                 if r['host'] == host and path.startswith(r['prefix']))
    config_path = 'services/' + route['service'] + '/config.yaml'
    config = load(Path(config_path))
    policy = dict(load(Path('platform/retry.yaml'))['retry'])
    policy.update(config.get('retry', {}))
    policy.update(config.get('environments', {}).get(environment, {}).get('retry', {}))
    policy.update(config.get('routes', {}).get(route['prefix'], {}).get('retry', {}))
    return dict(service=route['service'], config_path=config_path, retry=policy)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get('Host', '').split(':')[0]
        try:
            result = resolve(host, urlsplit(self.path).path, self.headers.get('X-Environment', 'production'))
        except (StopIteration, KeyError):
            self.send_error(404)
            return
        body = json.dumps(dict(result, upstream_status=502)).encode()
        response = json.loads(Path('gateway/response.json').read_text())
        self.send_response(502)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        for key, value in response.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--serve', action='store_true')
    p.add_argument('--port', type=int, default=8088)
    a = p.parse_args()
    if a.serve:
        server = HTTPServer(('127.0.0.1', a.port), Handler)
        print(server.server_port, flush=True)
        server.serve_forever()
    else:
        print(json.dumps(resolve('shop.internal', '/v1/checkout', 'production'), sort_keys=True))
