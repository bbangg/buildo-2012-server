#!/usr/bin/env python3
"""Log raw UDP datagrams on 17091 to inspect the client's ENet handshake."""
import socket, datetime
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
s.bind(("0.0.0.0",17091))
print("[udp] listening 0.0.0.0:17091", flush=True)
while True:
    d,a=s.recvfrom(4096)
    ts=datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[udp] {ts} {len(d)} bytes from {a}", flush=True)
    print("      hex: "+d[:64].hex(), flush=True)
    if len(d)>=4:
        peer=int.from_bytes(d[0:2],"little"); flags=int.from_bytes(d[0:2],"big")
        print(f"      peerID_le={peer} first4_be=0x{int.from_bytes(d[0:4],'big'):08x}", flush=True)
