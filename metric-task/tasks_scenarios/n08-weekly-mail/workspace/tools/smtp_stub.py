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
