"""Minimal SMTP sink used only on loopback; supports Python smtplib without external packages."""
import socketserver


class SMTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b"220 localhost local-sink\r\n")
        sender, recipients = '', []
        while True:
            line = self.rfile.readline()
            if not line:
                break
            text = line.decode().strip()
            command = text.split(' ', 1)[0].upper()
            if command in ('EHLO', 'HELO'):
                self.wfile.write(b"250 localhost\r\n")
            elif command == 'MAIL':
                sender, recipients = text.split(':', 1)[1].strip().strip('<>'), []
                self.wfile.write(b"250 accepted\r\n")
            elif command == 'RCPT':
                recipients.append(text.split(':', 1)[1].strip().strip('<>'))
                self.wfile.write(b"250 accepted\r\n")
            elif command == 'DATA':
                self.wfile.write(b"354 send message\r\n")
                data = []
                while True:
                    part = self.rfile.readline()
                    if not part or part == b'.\r\n':
                        break
                    data.append(part[1:] if part.startswith(b'..') else part)
                self.server.messages.append((sender, list(recipients), b''.join(data)))
                self.wfile.write(b"250 queued\r\n")
            elif command == 'QUIT':
                self.wfile.write(b"221 bye\r\n")
                break
            elif command in ('RSET', 'NOOP'):
                self.wfile.write(b"250 ok\r\n")
            else:
                self.wfile.write(b"502 unsupported\r\n")


def smtp_sink():
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), SMTPHandler)
    server.daemon_threads = True
    server.messages = []
    return server

from collections import Counter
from datetime import datetime
from email import policy
from email.parser import BytesParser
from pathlib import Path
import json
import secrets as random_values
import subprocess
import sys
import tempfile
import threading


def digest_behavior(ws, secrets):
    ws = Path(ws)
    for case in range(3):
        nonce = random_values.token_hex(5)
        users = [{'id': i, 'email': 'user-' + str(i) + '-' + nonce + '@local.test',
                  'active': i != 3, 'digest_opt_in': i != 2} for i in range(6)]
        actions = ['export-' + nonce, 'search-' + nonce, 'comment-' + nonce]
        events = []
        for i in range(5):
            for j in range(1 + i + case):
                events.append({'user_id': i, 'action': actions[j % 3], 'at': '2026-11-03T12:00:00Z'})
        events += [{'user_id': 0, 'action': 'start-' + nonce, 'at': '2026-11-02T00:00:00Z'},
                   {'user_id': 1, 'action': 'offset-' + nonce, 'at': '2026-11-02T02:00:00+02:00'},
                   {'user_id': 0, 'action': 'exclude-before', 'at': '2026-11-01T23:59:59Z'},
                   {'user_id': 0, 'action': 'exclude-end', 'at': '2026-11-09T00:00:00Z'},
                   {'user_id': 99, 'action': 'orphan', 'at': '2026-11-05T00:00:00Z'}]
        if case == 2:
            events = []
        start, end = '2026-11-02T00:00:00Z', '2026-11-09T00:00:00Z'
        def timestamp(value):
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        expected = {}
        for person in users:
            counts = Counter(e['action'] for e in events if e['user_id'] == person['id'] and
                             timestamp(start) <= timestamp(e['at']) < timestamp(end))
            if person['active'] and person['digest_opt_in'] and counts:
                expected[person['email']] = '\n'.join(f'{key}: {count}' for key, count in sorted(counts.items())) + '\n'
        server = smtp_sink()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                people, activity = Path(tmp) / 'users.json', Path(tmp) / 'events.json'
                people.write_text(json.dumps(users))
                activity.write_text(json.dumps(events))
                proc = subprocess.run([sys.executable, '-m', 'mail.weekly', '--start', start, '--end', end,
                    '--users', str(people), '--activities', str(activity), '--host', '127.0.0.1',
                    '--port', str(server.server_address[1])], cwd=ws, capture_output=True, timeout=10)
                if proc.returncode or len(server.messages) != len(expected):
                    return False, 'SMTP recipient count or command status differs'
                actual = {}
                for sender, recipients, data in server.messages:
                    message = BytesParser(policy=policy.default).parsebytes(data)
                    if len(recipients) != 1 or recipients[0] in actual or sender != 'digest@local.test':
                        return False, 'SMTP envelope differs or duplicate message'
                    if str(message['To']) != recipients[0] or str(message['Subject']) != 'Weekly activity 2026-11-02':
                        return False, 'message headers differ'
                    body = message.get_body(preferencelist=('plain',))
                    if body is None:
                        return False, 'missing plain digest body'
                    actual[recipients[0]] = body.get_content().replace('\r\n', '\n')
                if actual != expected:
                    return False, 'weekly interval, opt-in, grouping or ordering differs'
                if json.loads(people.read_text()) != users or json.loads(activity.read_text()) != events:
                    return False, 'input seed changed'
                for bad_start, bad_end in [(end, start), (start, start), ('2026-11-02T00:00:00', end)]:
                    before = len(server.messages)
                    bad = subprocess.run([sys.executable, '-m', 'mail.weekly', '--start', bad_start, '--end', bad_end,
                        '--users', str(people), '--activities', str(activity), '--host', '127.0.0.1',
                        '--port', str(server.server_address[1])], cwd=ws, capture_output=True, timeout=10)
                    if bad.returncode == 0 or len(server.messages) != before:
                        return False, 'invalid interval must fail before sending'
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return False, 'digest execution failed'
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    return True, 'actual SMTP envelopes, MIME bodies, opt-in and UTC interval verified'
