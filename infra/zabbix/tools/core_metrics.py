"""Print the latest CPU / MEM / DISK / NET values of one host from the Zabbix API (read-only).

usage: python core_metrics.py --host <host name in Zabbix> [--url <Zabbix API URL, default: env ZABBIX_URL or http://127.0.0.1:18080/api_jsonrpc.php>]
token: env ZABBIX_API_TOKEN, or --secrets <json with "api_token">
"""

import argparse
import json
import os
import sys
import time
import urllib.request

# (category, label, key match: exact key or prefix ending with '[')
CORE = [
    ("CPU", "CPU 사용률 (%)", "system.cpu.util"),
    ("CPU", "CPU 대기열 길이", 'perf_counter_en["\\System\\Processor Queue Length"]'),
    ("MEM", "메모리 사용률 (%)", "vm.memory.util"),
    ("MEM", "사용 메모리 (B)", "vm.memory.size[used]"),
    ("MEM", "전체 메모리 (B)", "vm.memory.size[total]"),
    (
        "MEM",
        "페이지 파일 사용률 (%)",
        'perf_counter_en["\\Paging file(_Total)\\% Usage"]',
    ),
    ("DISK", "드라이브 사용률 (%)", "vfs.fs.dependent.size[*,pused]"),
    ("DISK", "드라이브 여유 (B)", "vfs.fs.dependent.size[*,free]"),
    (
        "DISK",
        "디스크 읽기 지연 (s)",
        'perf_counter_en["\\PhysicalDisk(*)\\Avg. Disk sec/Read",60]',
    ),
    (
        "DISK",
        "디스크 쓰기 지연 (s)",
        'perf_counter_en["\\PhysicalDisk(*)\\Avg. Disk sec/Write",60]',
    ),
    ("NET", "수신 (bps)", 'net.if.in["*"]'),
    ("NET", "송신 (bps)", 'net.if.out["*"]'),
    ("NET", "수신 오류 (/s)", 'net.if.in["*",errors]'),
    ("NET", "링크 상태 (2=연결)", 'net.if.status["*"]'),
]


def match(pattern, key):
    if "*" not in pattern:
        return key == pattern
    head, tail = pattern.split("*", 1)
    return key.startswith(head) and key.endswith(tail)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", required=True)
    ap.add_argument(
        "--url",
        default=os.environ.get("ZABBIX_URL")
        or "http://127.0.0.1:18080/api_jsonrpc.php",
    )
    ap.add_argument("--secrets")
    a = ap.parse_args()
    token = (
        os.environ.get("ZABBIX_API_TOKEN")
        or json.load(open(a.secrets, encoding="utf-8"))["api_token"]
    )

    def call(method, params):
        req = urllib.request.Request(
            a.url,
            json.dumps(
                {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
            ).encode(),
            {
                "Content-Type": "application/json-rpc",
                "Authorization": f"Bearer {token}",
            },
        )
        r = json.loads(urllib.request.urlopen(req, timeout=20).read())
        if "error" in r:
            raise SystemExit(f"{method}: {r['error']}")
        return r["result"]

    hosts = call(
        "host.get",
        {"filter": {"host": [a.host]}, "output": ["hostid", "active_available"]},
    )
    if not hosts:
        raise SystemExit("host not found")
    items = call(
        "item.get",
        {
            "hostids": hosts[0]["hostid"],
            "output": ["key_", "lastvalue", "lastclock", "units", "state"],
        },
    )
    now = int(time.time())
    print(
        f"host={a.host} agent(active)={'OK' if hosts[0]['active_available'] == '1' else 'NOT OK (' + hosts[0]['active_available'] + ')'}"
    )
    for cat, label, pat in CORE:
        rows = [i for i in items if match(pat, i["key_"])]
        if not rows:
            print(f"[{cat}] {label}: (item 없음)")
        for i in rows:
            age = now - int(i["lastclock"]) if i["lastclock"] != "0" else None
            val = i["lastvalue"] if age is not None else "-"
            fresh = "아직 값 없음" if age is None else f"{age}s 전"
            print(f"[{cat}] {label}: {val} {i['units']}  ({fresh})  {i['key_']}")
    probs = call(
        "problem.get",
        {"hostids": hosts[0]["hostid"], "output": ["name", "severity", "clock"]},
    )
    print(
        f"열린 장애 {len(probs)}건"
        + "".join(f"\n  - [sev {p['severity']}] {p['name']}" for p in probs)
    )


if __name__ == "__main__":
    main()
