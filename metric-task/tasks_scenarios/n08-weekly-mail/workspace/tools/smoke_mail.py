import subprocess
import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.smtp_stub import smtp_sink

server = smtp_sink()
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    proc = subprocess.run([sys.executable, '-m', 'mail.weekly', '--start', '2026-11-02T00:00:00Z',
        '--end', '2026-11-09T00:00:00Z', '--users', 'fixtures/users.json', '--activities', 'fixtures/activities.json',
        '--host', '127.0.0.1', '--port', str(server.server_address[1])])
    if proc.returncode or len(server.messages) != 1:
        raise SystemExit(1)
    print('SMTP smoke received one digest')
finally:
    server.shutdown()
    server.server_close()
    thread.join()
