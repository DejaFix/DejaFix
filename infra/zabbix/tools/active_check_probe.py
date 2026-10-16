"""Ask a Zabbix server (or proxy) whether it knows a host, the same way an installed agent does.

Sends the agent's "active checks" request (read-only, same request the agent repeats every few seconds)
and prints the server's reply. Use the agent's exact Hostname so nothing new is sent to the server.

usage: python active_check_probe.py <server address> <agent Hostname> [--port 10051]
  response: success | items: N            -> the server knows the host, N active items
  response: failed  | info: host [...] not found -> no host with that technical "Host name" (case-sensitive)
"""

import argparse
import datetime
import json
import socket
import struct
import sys
import zlib

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("server")
    ap.add_argument("host")
    ap.add_argument("--port", type=int, default=10051)
    a = ap.parse_args()
    body = json.dumps(
        {"request": "active checks", "host": a.host, "version": "7.0.31", "variant": 1}
    ).encode()
    packet = b"ZBXD\x01" + struct.pack("<II", len(body), 0) + body
    with socket.create_connection((a.server, a.port), timeout=10) as s:
        s.sendall(packet)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    flags, size = data[4], struct.unpack("<I", data[5:9])[0]
    payload = data[13 : 13 + size]
    if flags & 0x02:
        payload = zlib.decompress(payload)
    r = json.loads(payload)
    print(
        datetime.datetime.now().strftime("%H:%M:%S"),
        "response:",
        r.get("response"),
        "| info:",
        r.get("info"),
        "| items:",
        len(r.get("data") or []),
    )


if __name__ == "__main__":
    main()
