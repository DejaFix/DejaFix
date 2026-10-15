"""DejaFix core-metrics dashboard: CPU / MEM / DISK / NET of one Zabbix host, served on 127.0.0.1 only.

The browser never sees the API token; this server calls the Zabbix API (read-only token) and returns a
summary JSON at /api/core. The page (index.html, same folder) polls it every 30 s.

usage:
  python server.py [--url <Zabbix API URL>] [--host <host name in Zabbix>] [--secrets <json>] [--port 18090]
  url:   --url, else env ZABBIX_URL, else the local dev server http://127.0.0.1:18080/api_jsonrpc.php
  host:  --host, else this PC's name (COMPUTERNAME)
  token: env ZABBIX_API_TOKEN, else "api_token" in --secrets (read-only token; never sent to the browser)
"""

import argparse
import json
import os
import pathlib
import socket
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
WINDOW_S = 3600  # sparkline window

# category -> metric definitions. pattern: exact key, or one '*' wildcard (per drive / interface)
# role "main" = card headline + sparkline; thresholds follow the "Windows by Zabbix agent active" 7.0 template
METRICS = {
    "cpu": [
        {
            "id": "util",
            "label": "CPU 사용률",
            "key": "system.cpu.util",
            "fmt": "pct",
            "role": "main",
            "crit": 90,
            "rule": "5분 동안 계속 90% 초과 → 경고",
        },
        {
            "id": "queue",
            "label": "CPU 대기열",
            "key": 'perf_counter_en["\\System\\Processor Queue Length"]',
            "fmt": "num",
            "rule": "5분 최솟값 − 코어×2 > 3 → 경고",
        },
    ],
    "mem": [
        {
            "id": "util",
            "label": "메모리 사용률",
            "key": "vm.memory.util",
            "fmt": "pct",
            "role": "main",
            "crit": 90,
            "rule": "5분 동안 계속 90% 초과 → 평균",
        },
        {
            "id": "used",
            "label": "사용 메모리",
            "key": "vm.memory.size[used]",
            "fmt": "bytes",
        },
        {
            "id": "total",
            "label": "전체 메모리",
            "key": "vm.memory.size[total]",
            "fmt": "bytes",
        },
        {
            "id": "page",
            "label": "페이지 파일 사용률",
            "key": 'perf_counter_en["\\Paging file(_Total)\\% Usage"]',
            "fmt": "pct",
            "rule": "여유 20% 미만 → 경고",
        },
    ],
    "disk": [
        {
            "id": "pused",
            "label": "드라이브 사용률",
            "key": "vfs.fs.dependent.size[*,pused]",
            "fmt": "pct",
            "role": "main",
            "warn": 80,
            "crit": 90,
            "rule": "5분 동안 계속 80% 초과 → 경고, 90% 초과 → 평균",
        },
        {
            "id": "free",
            "label": "드라이브 여유",
            "key": "vfs.fs.dependent.size[*,free]",
            "fmt": "bytes",
        },
        {
            "id": "rlat",
            "label": "읽기 지연",
            "key": 'perf_counter_en["\\PhysicalDisk(*)\\Avg. Disk sec/Read",60]',
            "fmt": "sec",
            "crit": 0.02,
            "rule": "15분 동안 계속 20ms 초과 → 경고",
        },
        {
            "id": "wlat",
            "label": "쓰기 지연",
            "key": 'perf_counter_en["\\PhysicalDisk(*)\\Avg. Disk sec/Write",60]',
            "fmt": "sec",
            "crit": 0.02,
            "rule": "15분 동안 계속 20ms 초과 → 경고",
        },
    ],
    "net": [
        {
            "id": "in",
            "label": "수신",
            "key": 'net.if.in["*"]',
            "fmt": "bps",
            "role": "main",
            "rule": "15분 평균이 링크 속도의 90% 초과 → 경고",
        },
        {
            "id": "out",
            "label": "송신",
            "key": 'net.if.out["*"]',
            "fmt": "bps",
            "role": "main",
        },
        {
            "id": "err_in",
            "label": "수신 오류",
            "key": 'net.if.in["*",errors]',
            "fmt": "rate",
            "crit": 2,
            "rule": "5분 동안 계속 초당 2개 초과 → 경고",
        },
        {
            "id": "err_out",
            "label": "송신 오류",
            "key": 'net.if.out["*",errors]',
            "fmt": "rate",
            "crit": 2,
        },
        {"id": "speed", "label": "링크 속도", "key": 'net.if.speed["*"]', "fmt": "bps"},
        {
            "id": "status",
            "label": "링크 상태",
            "key": 'net.if.status["*"]',
            "fmt": "linkstate",
            "rule": "2 = 연결됨, 바뀌면 링크 다운",
        },
    ],
}
CATEGORY_OF_PREFIX = [
    ("system.cpu", "cpu"),
    ('perf_counter_en["\\System\\Processor', "cpu"),
    ("vm.memory", "mem"),
    ("system.swap", "mem"),
    ('perf_counter_en["\\Paging', "mem"),
    ('perf_counter_en["\\Memory', "mem"),
    ("vfs.fs", "disk"),
    ('perf_counter_en["\\PhysicalDisk', "disk"),
    ("net.if", "net"),
]


def match(pattern, key):
    if "*" not in pattern:
        return (key == pattern, None)
    head, tail = pattern.split("*", 1)
    if (
        key.startswith(head)
        and key.endswith(tail)
        and len(key) >= len(head) + len(tail)
    ):
        return (True, key[len(head) : len(key) - len(tail)])
    return (False, None)


def category_of(key):
    for prefix, cat in CATEGORY_OF_PREFIX:
        if key.startswith(prefix):
            return cat
    return "other"


class Zabbix:
    def __init__(self, url, token):
        self.url, self.token = url, token

    def call(self, method, params, auth=True):
        headers = {"Content-Type": "application/json-rpc"}
        if auth:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps(
            {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        ).encode()
        with urllib.request.urlopen(
            urllib.request.Request(self.url, body, headers), timeout=15
        ) as r:
            resp = json.loads(r.read())
        if "error" in resp:
            raise RuntimeError(
                f"{method}: {resp['error'].get('message')} {resp['error'].get('data')}"
            )
        return resp["result"]


def build_summary(zbx, host_name):
    now = int(time.time())
    out = {
        "generated": now,
        "host": host_name,
        "source": zbx.url,
        "ok": True,
        "error": None,
    }
    out["version"] = zbx.call("apiinfo.version", {}, auth=False)
    hosts = zbx.call(
        "host.get",
        {
            "filter": {"host": [host_name]},
            "output": ["hostid", "active_available", "name"],
        },
    )
    if not hosts:
        raise RuntimeError(
            f"호스트 '{host_name}'를 찾을 수 없습니다 (토큰 사용자의 호스트 그룹 권한 확인)"
        )
    hostid = hosts[0]["hostid"]
    out["agent"] = {"active_available": int(hosts[0]["active_available"])}
    items = zbx.call(
        "item.get",
        {
            "hostids": hostid,
            "output": [
                "itemid",
                "key_",
                "value_type",
                "units",
                "lastclock",
                "lastvalue",
                "delay",
                "state",
                "error",
            ],
        },
    )
    ping = next((i for i in items if i["key_"] == "agent.ping"), None)
    out["agent"]["last_ping"] = (
        int(ping["lastclock"]) if ping and ping["lastclock"] != "0" else None
    )

    cats, series_ids = {}, {}
    for cat, defs in METRICS.items():
        rows = []
        for d in defs:
            for it in items:
                ok, inst = match(d["key"], it["key_"])
                if not ok:
                    continue
                last = int(it["lastclock"])
                row = {
                    "id": d["id"],
                    "label": d["label"],
                    "instance": inst,
                    "key": it["key_"],
                    "fmt": d["fmt"],
                    "units": it["units"],
                    "value": float(it["lastvalue"]) if last else None,
                    "clock": last or None,
                    "state": int(it["state"]),
                    "error": it["error"] or None,
                    "main": d.get("role") == "main",
                    "warn": d.get("warn"),
                    "crit": d.get("crit"),
                    "rule": d.get("rule"),
                }
                if row["main"] and last:
                    series_ids[it["itemid"]] = (int(it["value_type"]), row)
                rows.append(row)
            if not any(r["id"] == d["id"] for r in rows):
                rows.append(
                    {
                        "id": d["id"],
                        "label": d["label"],
                        "instance": None,
                        "key": d["key"],
                        "fmt": d["fmt"],
                        "value": None,
                        "clock": None,
                        "missing": True,
                        "main": d.get("role") == "main",
                        "warn": d.get("warn"),
                        "crit": d.get("crit"),
                        "rule": d.get("rule"),
                    }
                )
        cats[cat] = {"metrics": rows, "problems": []}

    # history for headline metrics, one call per value type (history.get takes a single type)
    by_type = {}
    for itemid, (vt, row) in series_ids.items():
        by_type.setdefault(vt, []).append(itemid)
        row["series"] = []
    for vt, ids in by_type.items():
        hist = zbx.call(
            "history.get",
            {
                "history": vt,
                "itemids": ids,
                "time_from": now - WINDOW_S,
                "time_till": now,
                "output": ["itemid", "clock", "value"],
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": 5000,
            },
        )
        for h in hist:
            series_ids[h["itemid"]][1]["series"].append(
                [int(h["clock"]), float(h["value"])]
            )

    problems = zbx.call(
        "problem.get",
        {
            "hostids": hostid,
            "output": [
                "eventid",
                "objectid",
                "name",
                "severity",
                "clock",
                "acknowledged",
            ],
            "sortfield": ["eventid"],
            "sortorder": "DESC",
        },
    )
    trig = {}
    if problems:
        for t in zbx.call(
            "trigger.get",
            {
                "triggerids": [p["objectid"] for p in problems],
                "output": ["triggerid"],
                "selectItems": ["key_"],
            },
        ):
            trig[t["triggerid"]] = [i["key_"] for i in t["items"]]
    out["problems"] = []
    for p in problems:
        keys = trig.get(p["objectid"], [])
        cat = next((category_of(k) for k in keys if category_of(k) != "other"), "other")
        prob = {
            "name": p["name"],
            "severity": int(p["severity"]),
            "clock": int(p["clock"]),
            "category": cat,
            "items": keys,
        }
        out["problems"].append(prob)
        if cat in cats:
            cats[cat]["problems"].append(prob)
    out["categories"] = cats
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--url",
        default=os.environ.get("ZABBIX_URL")
        or "http://127.0.0.1:18080/api_jsonrpc.php",
        help="Zabbix API URL (default: env ZABBIX_URL, else the local dev server)",
    )
    ap.add_argument(
        "--host",
        default=os.environ.get("COMPUTERNAME") or socket.gethostname(),
        help="technical host name in Zabbix (default: this PC's name)",
    )
    ap.add_argument(
        "--secrets",
        help='JSON file with "api_token" (used only when ZABBIX_API_TOKEN is not set)',
    )
    ap.add_argument("--port", type=int, default=18090)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    token = os.environ.get("ZABBIX_API_TOKEN")
    if not token and a.secrets:
        token = json.loads(pathlib.Path(a.secrets).read_text(encoding="utf-8"))[
            "api_token"
        ]
    if not token:
        sys.exit(
            "read-only API token missing: set ZABBIX_API_TOKEN (or pass --secrets <json>)"
        )
    zbx = Zabbix(a.url, token)
    cache = {"t": 0, "body": b""}
    lock = threading.Lock()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(
                    200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8"
                )
            if self.path.startswith("/api/core"):
                with lock:
                    if time.time() - cache["t"] > 10:
                        try:
                            data = build_summary(zbx, a.host)
                        except Exception as e:  # noqa: BLE001  (shown on the page as a connection error)
                            data = {
                                "ok": False,
                                "error": str(e),
                                "generated": int(time.time()),
                                "host": a.host,
                                "source": a.url,
                            }
                        cache["body"], cache["t"] = (
                            json.dumps(data, ensure_ascii=False).encode("utf-8"),
                            time.time(),
                        )
                    body = cache["body"]
                return self.send(200, body, "application/json; charset=utf-8")
            return self.send(404, b"not found", "text/plain")

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(
        f"DejaFix dashboard: http://127.0.0.1:{a.port}  (source {a.url}, host {a.host})",
        flush=True,
    )
    srv.serve_forever()


if __name__ == "__main__":
    main()
