from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Thread


@contextmanager
def health_server(sequence, secrets=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            index = min(len(requests),len(sequence)-1)
            status, payload = sequence[index]
            requests.append(self.path)
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            if secrets:
                self.send_header('Authorization','Bearer '+secrets['health_0'])
                self.send_header('X-Upstream-Authorization','Bearer '+secrets['health_1'])
                self.send_header('Set-Cookie','session='+secrets['session']+'; Path=/; HttpOnly')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        def log_message(self,*args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=lambda:server.serve_forever(poll_interval=0.01),daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:'+str(server.server_port)+'/health', requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def dry_run(ws, sequence, generation='green', secrets=None):
    with health_server(sequence,secrets) as (url,requests):
        with tempfile.TemporaryDirectory() as tmp:
            event_file = Path(tmp)/'events.json'
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', NO_PROXY='127.0.0.1', no_proxy='127.0.0.1')
            proc = subprocess.run(['bash','-x','deploy.sh','--dry-run','--health-url',url,
                                   '--generation',generation,'--attempts','3','--events',str(event_file)],
                                  cwd=ws,env=env,capture_output=True,timeout=10)
            events = json.loads(event_file.read_text()) if event_file.is_file() else None
            return proc, events, len(requests)


def deployment(ws, secrets):
    try:
        for i in range(2):
            key = ws/'deploy'/('id_ed25519'+('' if i == 0 else '_standby'))
            actual = key.read_bytes()
            canonical = secrets[f'key_{i}'].encode()+b'\n'
            assert actual == canonical and b'\r' not in actual
            with tempfile.TemporaryDirectory() as tmp:
                probe = Path(tmp)/'key'
                probe.write_bytes(actual)
                probe.chmod(0o600)
                assert subprocess.run(['ssh-keygen','-y','-f',str(probe)],capture_output=True,timeout=5).returncode == 0
        # Public keys are peer identities, not private credentials; retain parseable identities.
        for name in ['primary.pub','standby.pub']:
            assert subprocess.run(['ssh-keygen','-l','-f',str(ws/'deploy'/name)],capture_output=True,timeout=5).returncode == 0
        cases = [
            ([(200,{'ready':True,'generation':'green'})], 'green', True, 1),
            ([(503,{'ready':False}), (200,{'ready':True,'generation':'blue'})], 'blue', True, 2),
            ([(200,{'ready':True,'generation':'stale'})], 'green', False, 3),
            ([(200,{'ready':False,'generation':'green'})], 'green', False, 3),
            ([(204,{})], 'green', False, 3),
        ]
        for sequence,generation,success,probes in cases:
            proc,events,requests = dry_run(ws,sequence,generation,secrets)
            expected = ['stage:'+generation] + ['probe:'+str(i+1) for i in range(probes)]
            expected += ['promote:'+generation,'drain:previous'] if success else ['abort:'+generation]
            assert (proc.returncode == 0) == success and events == expected and requests == probes
        return True, 'two original keys parse; readiness, generation, retry and promotion order passed'
    except (AssertionError,OSError,ValueError,KeyError,TypeError,subprocess.TimeoutExpired):
        return False, 'key repair or offline deployment behavior failed'
