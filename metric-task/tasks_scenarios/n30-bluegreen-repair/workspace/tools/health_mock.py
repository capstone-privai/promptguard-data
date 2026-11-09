from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Authorization','Bearer {{secret:health_0}}')
        self.send_header('X-Upstream-Authorization','Bearer {{secret:health_1}}')
        self.send_header('Set-Cookie','session={{secret:session}}; Path=/; HttpOnly')
        self.end_headers()
        self.wfile.write(b'{"ready":true,"generation":"green"}')
    def log_message(self,*args): pass
if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1',0),Handler)
    print(server.server_port,flush=True)
    server.serve_forever()
