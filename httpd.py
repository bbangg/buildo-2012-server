#!/usr/bin/env python3
"""server_data.php stand-in for Buildo (2012). Body + header style are read
from disk on every request so variants can be tried without a restart."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pathlib, sys

HERE = pathlib.Path(__file__).parent
BODY_F = HERE/"response.txt"
MODE_F = HERE/"mode.txt"          # one of: h10, h11close, minimal, noclen

class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def _serve(self, verb):
        n = int(self.headers.get("Content-Length") or 0)
        post = self.rfile.read(n) if n else b""
        body = BODY_F.read_bytes()
        mode = MODE_F.read_text().strip() if MODE_F.exists() else "h10"
        print(f"[http] {verb} {self.path} post={post!r} mode={mode} len={len(body)}", flush=True)
        for k, v in self.headers.items():
            print(f"       > {k}: {v}", flush=True)

        if mode == "minimal":
            head = b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
            self.wfile.write(head + body); self.wfile.flush()
            self.close_connection = True
            return
        if mode == "noclen":
            self.wfile.write(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n" + body)
            self.wfile.flush(); self.close_connection = True
            return
        if mode == "h11close":
            self.protocol_version = "HTTP/1.1"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def do_POST(self): self._serve("POST")
    def do_GET(self):  self._serve("GET")
    def log_message(self, *a): pass

if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8080), H)
    print("[http] listening 127.0.0.1:8080", flush=True)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass
