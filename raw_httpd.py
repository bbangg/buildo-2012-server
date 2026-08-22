#!/usr/bin/env python3
"""Raw TCP stand-in for server_data.php. Logs the exact bytes the Buildo
client sends (no HTTP library to silently reject malformed requests)."""
import socket, threading, pathlib, sys, os, datetime

HERE = pathlib.Path(__file__).parent
PORT = int(os.environ.get("BUILDO_HTTP_PORT", 8081))  # keep in sync with patch_client.HTTP_PORT
BODY = (HERE/"response.txt").read_bytes()

def handle(c, a):
    c.settimeout(4)
    data = b""
    try:
        while b"\r\n\r\n" not in data and b"\n\n" not in data and len(data) < 8192:
            ch = c.recv(4096)
            if not ch: break
            data += ch
    except Exception as e:
        print(f"[raw] recv error from {a}: {e}", flush=True)
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[raw] {ts} conn from {a}, {len(data)} bytes:", flush=True)
    print("      " + repr(data), flush=True)
    body = (HERE/"response.txt").read_bytes()
    resp = (b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + body)
    try:
        c.sendall(resp)
        print(f"[raw] replied {len(resp)} bytes (body {len(body)})", flush=True)
    except Exception as e:
        print(f"[raw] send error: {e}", flush=True)
    try: c.shutdown(socket.SHUT_WR)
    except Exception: pass
    c.close()

s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", PORT))
s.listen(16)
print(f"[raw] listening 0.0.0.0:{PORT}", flush=True)
while True:
    c, a = s.accept()
    threading.Thread(target=handle, args=(c,a), daemon=True).start()
