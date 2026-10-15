"""Local stand-in for the server side of Zabbix *active* checks (TEST ONLY, not a Zabbix server).

Use it to check active-only items such as eventlog[] on an agent before the team's Zabbix server exists.
It hands the agent a fixed item list, then records every "agent data" value it receives.
Protocol: https://www.zabbix.com/documentation/7.0/en/manual/appendix/items/activepassive
Header:   https://www.zabbix.com/documentation/7.0/en/manual/appendix/protocols/header_datalen

usage:
  python mock_active_server.py --items items.json --out received.jsonl [--listen 127.0.0.1] [--port 10051] [--seconds 300]

items.json: [{"key": "eventlog[System,,\\"Warning|Error|Critical\\"]", "delay": "10s", "lastlogsize": 0}, ...]
"""

import argparse
import json
import socket
import struct
import threading
import time
import zlib


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed early")
        buf += chunk
    return buf


def read_packet(conn):
    head = recv_exact(conn, 5)
    if head[:4] != b"ZBXD":
        raise ValueError(f"bad header {head!r}")
    flags = head[4]
    if flags & 0x04:  # large packet: 8-byte lengths
        datalen, reserved = struct.unpack("<QQ", recv_exact(conn, 16))
    else:
        datalen, reserved = struct.unpack("<II", recv_exact(conn, 8))
    data = recv_exact(conn, datalen)
    if flags & 0x02:
        data = zlib.decompress(data)
    return flags, json.loads(data.decode("utf-8"))


def send_packet(conn, obj):
    data = json.dumps(obj).encode("utf-8")
    conn.sendall(b"ZBXD\x01" + struct.pack("<II", len(data), 0) + data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--listen", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10051)
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument(
        "--fail-info",
        help='answer every "active checks" request with response=failed and this info '
        '(e.g. "host [X] not found") to see how the agent logs it',
    )
    a = ap.parse_args()

    items = json.load(open(a.items, encoding="utf-8"))
    checks = [
        {
            "key": it["key"],
            "itemid": 1000 + i,
            "delay": it.get("delay", "30s"),
            "lastlogsize": it.get("lastlogsize", 0),
            "mtime": 0,
        }
        for i, it in enumerate(items)
    ]
    keys = {c["itemid"]: c["key"] for c in checks}
    revision = 1
    lock = threading.Lock()
    out = open(a.out, "a", encoding="utf-8")

    def log(kind, payload):
        with lock:
            out.write(
                json.dumps(
                    {"t": round(time.time(), 3), "kind": kind, **payload},
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.flush()

    def handle(conn):
        with conn:
            try:
                flags, req = read_packet(conn)
            except Exception as e:  # noqa: BLE001
                log("error", {"error": str(e)})
                return
            kind = req.get("request")
            if kind == "active checks":
                log(
                    "active_checks_request",
                    {
                        "flags": flags,
                        "request": {k: v for k, v in req.items() if k != "session"},
                    },
                )
                if a.fail_info:
                    send_packet(conn, {"response": "failed", "info": a.fail_info})
                elif req.get("config_revision") == revision:
                    send_packet(
                        conn, {"response": "success"}
                    )  # unchanged configuration
                else:
                    send_packet(
                        conn,
                        {
                            "response": "success",
                            "config_revision": revision,
                            "data": checks,
                        },
                    )
            elif kind == "agent data":
                for v in req.get("data", []):
                    log("value", {"key": keys.get(v.get("itemid"), "?"), **v})
                send_packet(
                    conn,
                    {
                        "response": "success",
                        "info": f"processed: {len(req.get('data', []))}; failed: 0; total: {len(req.get('data', []))}; seconds spent: 0.000001",
                    },
                )
            elif kind == "active check heartbeat":
                log("heartbeat", {"request": req})
                send_packet(conn, {"response": "success"})
            else:
                log("unknown", {"request": req})
                send_packet(conn, {"response": "failed", "info": "unsupported request"})

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind((a.listen, a.port))
    srv.listen(16)
    srv.settimeout(1.0)
    log("started", {"listen": f"{a.listen}:{a.port}", "items": checks})
    deadline = time.time() + a.seconds
    while time.time() < deadline:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        threading.Thread(target=handle, args=(conn,), daemon=True).start()
    log("stopped", {})
    srv.close()


if __name__ == "__main__":
    main()
