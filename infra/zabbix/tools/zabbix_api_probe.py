"""Read-only check of the 7 Zabbix API methods the platform uses (host/item/history/trend/problem/event/trigger.get).

The URL and token come from environment variables, so nothing secret lands in files or shell history:
  ZABBIX_API_URL    e.g. https://<zabbix-frontend>/api_jsonrpc.php
  ZABBIX_API_TOKEN  API token from Users > API tokens (use a read-only user, see docs/zabbix/windows-agent-api.md)

usage:
  python zabbix_api_probe.py --host <technical host name> [--hours 6] [--days 7] [--out probe_out] [--insecure]
  python zabbix_api_probe.py --dry-run --out requests_dir      # write the request bodies only, no network

Only *.get methods and apiinfo.version are called. IPv4/IPv6 addresses are masked in saved responses.
"""

import argparse
import json
import os
import pathlib
import re
import ssl
import sys
import time
import urllib.request

# Item keys the platform reads first (Windows template keys; LLD keys are matched by prefix)
CORE_KEYS = [
    "agent.ping",
    "system.cpu.util",
    "system.cpu.load",
    'perf_counter_en["\\System\\Processor Queue Length"]',
    "vm.memory.size[total]",
    "vm.memory.size[used]",
    "vm.memory.util",
    "system.swap.pfree",
    "system.uptime",
    "system.hostname",
    "system.sw.os",
    "proc.num[]",
]
CORE_PREFIXES = [
    "vfs.fs.dependent.size[",
    'perf_counter_en["\\PhysicalDisk(',
    "net.if.in[",
    "net.if.out[",
    "service.info[",
    "eventlog[",
]

IPV4 = re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")


def mask(obj):
    return json.loads(
        IPV6.sub("<ipv6>", IPV4.sub("<ipv4>", json.dumps(obj, ensure_ascii=False)))
    )


class Api:
    def __init__(self, url, token, insecure=False, dry_dir=None):
        self.url, self.token, self.dry_dir, self.n = url, token, dry_dir, 0
        self.ctx = ssl._create_unverified_context() if insecure else None  # noqa: SLF001 (lab servers with self-signed certs)

    def call(self, method, params, name=None, auth=True):
        self.n += 1
        body = {"jsonrpc": "2.0", "method": method, "params": params, "id": self.n}
        if self.dry_dir:
            (self.dry_dir / f"{self.n:02d}-{name or method}.json").write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return None
        headers = {"Content-Type": "application/json-rpc"}
        if auth:
            headers["Authorization"] = (
                f"Bearer {self.token}"  # the "auth" body property was removed in 7.2
            )
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=30, context=self.ctx) as r:
            resp = json.loads(r.read().decode("utf-8"))
        ms = round((time.perf_counter() - t0) * 1000)
        if "error" in resp:
            raise RuntimeError(
                f"{method}: {resp['error'].get('message')} {resp['error'].get('data')}"
            )
        return resp["result"], ms


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--host",
        help="technical host name (host.host) to inspect; default: first host returned",
    )
    ap.add_argument("--hours", type=int, default=6, help="history window")
    ap.add_argument("--days", type=int, default=7, help="trend / event window")
    ap.add_argument("--out", default="probe_out")
    ap.add_argument(
        "--insecure", action="store_true", help="skip TLS verification (lab only)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="write request bodies to --out and exit"
    )
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    now = int(time.time())
    if a.dry_run:
        api = Api(None, None, dry_dir=out)
        hostid, itemids_by_type = (
            "<hostid>",
            {0: ["<itemid>"], 3: ["<itemid>"], 2: ["<itemid>"]},
        )
    else:
        url, token = (
            os.environ.get("ZABBIX_API_URL"),
            os.environ.get("ZABBIX_API_TOKEN"),
        )
        if not url or not token:
            sys.exit("set ZABBIX_API_URL and ZABBIX_API_TOKEN first")
        api = Api(url, token, insecure=a.insecure)

    report = {}

    def run(name, method, params, auth=True):
        res = api.call(method, params, name=name, auth=auth)
        if res is None:
            return None
        result, ms = res
        (out / f"{name}.json").write_text(
            json.dumps(mask(result), ensure_ascii=False, indent=1), encoding="utf-8"
        )
        report[name] = {
            "ms": ms,
            "count": len(result) if isinstance(result, list) else 1,
        }
        return result

    version = run(
        "apiinfo.version", "apiinfo.version", {}, auth=False
    )  # must be called without auth

    host_params = {
        "output": [
            "hostid",
            "host",
            "name",
            "status",
            "active_available",
            "maintenance_status",
        ],
        "selectInterfaces": [
            "interfaceid",
            "type",
            "main",
            "useip",
            "ip",
            "dns",
            "port",
            "available",
            "error",
        ],
        "selectHostGroups": ["groupid", "name"],
        "selectParentTemplates": ["templateid", "name"],
        "selectTags": ["tag", "value"],
        "sortfield": "host",
        "limit": 50,
    }
    if a.host:
        host_params["filter"] = {"host": [a.host]}
    hosts = run("host.get", "host.get", host_params)
    if hosts is not None:
        if not hosts:
            sys.exit(
                "host.get returned nothing (check host name and the token user's host group permissions)"
            )
        hostid = hosts[0]["hostid"]

    items = run(
        "item.get",
        "item.get",
        {
            "output": [
                "itemid",
                "key_",
                "name",
                "type",
                "value_type",
                "units",
                "delay",
                "history",
                "trends",
                "status",
                "state",
                "error",
                "lastclock",
                "lastvalue",
            ],
            "hostids": hostid,
            "sortfield": "key_",
        },
    )
    if items is not None:
        itemids_by_type = {}
        for it in items:
            core = it["key_"] in CORE_KEYS or any(
                it["key_"].startswith(p) for p in CORE_PREFIXES
            )
            if core and it["status"] == "0":
                itemids_by_type.setdefault(int(it["value_type"]), []).append(
                    it["itemid"]
                )
        report["item.get"]["by_value_type"] = {
            str(k): len(v) for k, v in sorted(itemids_by_type.items())
        }
        report["item.get"]["not_supported"] = sum(
            1 for it in items if it["state"] == "1"
        )

    # history.get returns only ONE value type per call (default 3 = numeric unsigned) -> one call per type
    for vtype, ids in sorted(itemids_by_type.items()):
        run(
            f"history.get.type{vtype}",
            "history.get",
            {
                "output": "extend",
                "history": vtype,
                "itemids": ids,
                "time_from": now - a.hours * 3600,
                "time_till": now,
                "sortfield": "clock",
                "sortorder": "DESC",
                "limit": 1000,
            },
        )
    numeric = itemids_by_type.get(0, []) + itemids_by_type.get(
        3, []
    )  # trends exist only for numeric items
    if numeric:
        run(
            "trend.get",
            "trend.get",
            {
                "output": [
                    "itemid",
                    "clock",
                    "num",
                    "value_min",
                    "value_avg",
                    "value_max",
                ],
                "itemids": numeric,
                "time_from": now - a.days * 86400,
                "time_till": now,
                "limit": 5000,
            },
        )

    run(
        "problem.get",
        "problem.get",
        {
            "output": "extend",
            "hostids": hostid,
            "recent": True,
            "selectTags": "extend",
            "selectAcknowledges": ["clock", "message", "action"],
            "sortfield": ["eventid"],
            "sortorder": "DESC",
            "limit": 50,
        },
    )
    run(
        "event.get",
        "event.get",
        {
            "output": [
                "eventid",
                "source",
                "object",
                "objectid",
                "clock",
                "value",
                "severity",
                "name",
                "r_eventid",
                "acknowledged",
            ],
            "hostids": hostid,
            "source": 0,
            "object": 0,
            "value": [0, 1],
            "time_from": now - a.days * 86400,
            "time_till": now,
            "selectHosts": ["hostid", "host", "name"],
            "selectRelatedObject": ["triggerid", "description", "priority", "value"],
            "selectTags": "extend",
            "sortfield": ["clock", "eventid"],
            "sortorder": "DESC",
            "limit": 100,
        },
    )
    triggers = run(
        "trigger.get",
        "trigger.get",
        {
            "output": [
                "triggerid",
                "description",
                "priority",
                "value",
                "status",
                "state",
                "lastchange",
                "error",
                "expression",
            ],
            "hostids": hostid,
            "expandDescription": True,
            "expandExpression": True,
            "selectItems": ["itemid", "key_", "value_type", "units"],
            "selectHosts": ["hostid", "host"],
            "selectTags": "extend",
            "sortfield": "priority",
            "sortorder": "DESC",
            "limit": 200,
        },
    )
    if triggers is not None:
        report["trigger.get"]["in_problem"] = sum(
            1 for t in triggers if t["value"] == "1"
        )

    if a.dry_run:
        print(f"wrote {api.n} request bodies to {out}")
        return
    report["apiinfo.version"]["value"] = version
    (out / "summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
