"""Ask a running Zabbix agent for item values (passive checks via zabbix_get) and record what this host really returns.

Runs every key twice: the first pass registers collector-based keys (CPU, perf counters),
the second pass (after --warmup seconds) is the one that is reported.
IPv4/IPv6/MAC addresses are masked in the saved output.

usage:
  python verify_agent_items.py --zabbix-get C:\\path\\zabbix_get.exe --out results_dir
         [--host 127.0.0.1] [--port 10050] [--warmup 65]
"""

import argparse
import datetime
import json
import pathlib
import re
import subprocess
import time

# (category, key, where it comes from)
#   template = used by the official "Windows by Zabbix agent" 7.0 template
#   extra    = not in the template, checked for incident analysis
#   expect-unsupported = documented as not supported on Windows, checked to confirm
STATIC_KEYS = [
    ("agent", "agent.ping", "template"),
    ("agent", "agent.version", "template"),
    ("agent", "agent.variant", "extra"),
    ("agent", "agent.hostname", "template"),
    ("system", "system.hostname", "template"),
    ("system", "system.hostname[fqdn]", "extra"),
    ("system", "system.uname", "template"),
    ("system", "system.sw.os", "template"),
    ("system", "system.sw.os.get", "extra"),
    ("system", "system.sw.arch", "template"),
    ("system", "system.uptime", "template"),
    ("system", "system.localtime", "template"),
    ("system", "system.boottime", "expect-unsupported"),
    ("system", "system.users.num", "extra"),
    (
        "system",
        'wmi.get[root\\cimv2,"select LastBootUpTime from Win32_OperatingSystem"]',
        "extra",
    ),
    (
        "system",
        'registry.data["HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion",DisplayVersion]',
        "extra",
    ),
    ("cpu", "system.cpu.util", "template"),
    ("cpu", "system.cpu.util[,system]", "extra"),
    ("cpu", "system.cpu.util[0]", "extra"),
    ("cpu", "system.cpu.util[,user]", "expect-unsupported"),
    ("cpu", "system.cpu.util[,,avg5]", "expect-unsupported"),
    ("cpu", "system.cpu.load", "extra"),
    ("cpu", "system.cpu.load[percpu,avg1]", "extra"),
    ("cpu", "system.cpu.load[all,avg5]", "extra"),
    ("cpu", "system.cpu.num", "extra"),
    ("cpu", "system.cpu.discovery", "extra"),
    (
        "cpu",
        'wmi.get[root/cimv2,"Select NumberOfLogicalProcessors from Win32_ComputerSystem"]',
        "template",
    ),
    (
        "cpu",
        'perf_counter_en["\\Processor Information(_total)\\% Processor Time"]',
        "extra",
    ),
    (
        "cpu",
        'perf_counter_en["\\Processor Information(_total)\\% Processor Utility"]',
        "extra",
    ),
    (
        "cpu",
        'perf_counter_en["\\Processor Information(_total)\\% User Time"]',
        "template",
    ),
    (
        "cpu",
        'perf_counter_en["\\Processor Information(_total)\\% Privileged Time"]',
        "template",
    ),
    (
        "cpu",
        'perf_counter_en["\\Processor Information(_total)\\% Interrupt Time"]',
        "template",
    ),
    (
        "cpu",
        'perf_counter_en["\\Processor Information(_total)\\% DPC Time"]',
        "template",
    ),
    ("cpu", 'perf_counter_en["\\System\\Processor Queue Length"]', "template"),
    ("cpu", 'perf_counter_en["\\System\\Context Switches/sec"]', "template"),
    ("cpu", 'perf_counter["\\Processor(_Total)\\% Processor Time"]', "extra"),
    ("memory", "vm.memory.size[total]", "template"),
    ("memory", "vm.memory.size[used]", "template"),
    ("memory", "vm.memory.size[available]", "extra"),
    ("memory", "vm.memory.size[free]", "extra"),
    ("memory", "vm.memory.size[pused]", "extra"),
    ("memory", "vm.memory.size[pavailable]", "extra"),
    ("memory", "vm.memory.util", "expect-unsupported"),
    ("memory", "vm.vmemory.size[total]", "extra"),
    ("memory", "vm.vmemory.size[used]", "extra"),
    ("memory", "vm.vmemory.size[available]", "extra"),
    ("memory", "vm.vmemory.size[pused]", "extra"),
    ("memory", "system.swap.size[,total]", "template"),
    ("memory", "system.swap.size[,free]", "extra"),
    ("memory", "system.swap.size[,pfree]", "extra"),
    ("memory", "system.swap.size[,pused]", "extra"),
    ("memory", 'perf_counter_en["\\Paging file(_Total)\\% Usage"]', "template"),
    ("memory", 'perf_counter_en["\\Memory\\Cache Bytes"]', "template"),
    (
        "memory",
        'perf_counter_en["\\Memory\\Free System Page Table Entries"]',
        "template",
    ),
    ("memory", 'perf_counter_en["\\Memory\\Page Faults/sec"]', "template"),
    ("memory", 'perf_counter_en["\\Memory\\Pages/sec"]', "template"),
    ("memory", 'perf_counter_en["\\Memory\\Pool Nonpaged Bytes"]', "template"),
    ("memory", 'perf_counter_en["\\Memory\\Available MBytes"]', "extra"),
    ("memory", 'perf_counter_en["\\Memory\\% Committed Bytes In Use"]', "extra"),
    ("disk", "vfs.fs.discovery", "extra"),
    ("disk", "vfs.fs.get", "template"),
    ("disk", "vfs.fs.size[C:,total]", "extra"),
    ("disk", "vfs.fs.size[C:,used]", "extra"),
    ("disk", "vfs.fs.size[C:,free]", "extra"),
    ("disk", "vfs.fs.size[C:,pused]", "extra"),
    ("disk", "vfs.fs.size[C:,pfree]", "extra"),
    ("disk", "vfs.fs.inode[C:,pfree]", "expect-unsupported"),
    ("disk", "perf_instance_en.discovery[PhysicalDisk]", "template"),
    ("disk", "vfs.dev.discovery", "expect-unsupported"),
    ("disk", "vfs.dev.read[,ops]", "expect-unsupported"),
    (
        "disk",
        'wmi.getall[root\\cimv2,"select Index,Model,Status,Size from Win32_DiskDrive"]',
        "extra",
    ),
    ("network", "net.if.discovery", "template"),
    ("network", "net.if.list", "extra"),
    (
        "network",
        'wmi.getall[root\\cimv2,"select Name,Description,NetConnectionID,Speed,AdapterTypeId,NetConnectionStatus,GUID from win32_networkadapter where PhysicalAdapter=True and NetConnectionStatus>0"]',
        "template",
    ),
    ("network", "net.tcp.port[127.0.0.1,10050]", "extra"),
    ("network", "net.tcp.listen[10050]", "extra"),
    ("network", "net.tcp.socket.count[,10050]", "extra"),
    ("network", "net.dns[,www.zabbix.com,A,2,1]", "extra"),
    ("service", "service.discovery", "template"),
    ("service", "service.info[EventLog]", "extra"),
    ("service", "service.info[EventLog,startup]", "extra"),
    ("service", "service.info[Dnscache,state]", "extra"),
    ("service", "service.info[Winmgmt,displayname]", "extra"),
    ("service", "service.info[NoSuchService_DejaFix]", "extra"),
    ("service", "services[automatic,stopped]", "extra"),
    ("process", "proc.num[]", "template"),
    ("process", "proc.num[svchost.exe]", "extra"),
    ("process", 'perf_counter_en["\\System\\Threads"]', "template"),
    ("process", 'perf_counter_en["\\System\\Processes"]', "extra"),
    ("process", "proc_info[svchost.exe,wkset,sum]", "extra"),
    ("process", "proc_info[svchost.exe,io_read_b,sum]", "extra"),
    ("process", "proc_info[svchost.exe,utime,sum]", "extra"),
    ("process", "proc.get[,,,summary]", "extra"),
    ("process", 'perf_counter_en["\\Process(svchost)\\% Processor Time",60]', "extra"),
    (
        "process",
        "wmi.getall[root\\cimv2,\"select Name,IDProcess,PercentProcessorTime,WorkingSetPrivate from Win32_PerfFormattedData_PerfProc_Process where Name<>'_Total' and Name<>'Idle' and PercentProcessorTime>0\"]",
        "extra",
    ),
    ("process", "proc.cpu.util[]", "expect-unsupported"),
    ("process", "proc.mem[]", "expect-unsupported"),
    ("eventlog", "eventlog[System]", "expect-unsupported"),
]

DISK_COUNTERS = [
    ("Disk Reads/sec", "template"),
    ("Disk Writes/sec", "template"),
    ("Current Disk Queue Length", "template"),
    ("% Idle Time", "template"),
    ("Avg. Disk sec/Read", "template"),
    ("Avg. Disk sec/Write", "template"),
    ("Avg. Disk Read Queue Length", "template"),
    ("Avg. Disk Write Queue Length", "template"),
    ("Disk Read Bytes/sec", "extra"),
    ("Disk Write Bytes/sec", "extra"),
]

IPV4 = re.compile(r"\b(?!127\.0\.0\.1\b)(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(
    r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b|\bfe80::[0-9a-fA-F:%]+"
)
MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


def mask(text):
    return MAC.sub("<mac>", IPV6.sub("<ipv6>", IPV4.sub("<ipv4>", text)))


def zabbix_get(exe, host, port, key, timeout):
    t0 = time.perf_counter()
    p = subprocess.run(
        [exe, "-s", host, "-p", str(port), "-t", str(timeout), "-k", key],
        capture_output=True,
        timeout=timeout + 15,
    )
    ms = round((time.perf_counter() - t0) * 1000)
    out = (p.stdout or b"").decode("utf-8", errors="replace").strip()
    err = (p.stderr or b"").decode("utf-8", errors="replace").strip()
    if p.returncode != 0 and not out:
        return {"ok": False, "error": err or f"exit {p.returncode}", "ms": ms}
    if out.startswith("ZBX_NOTSUPPORTED"):
        return {"ok": False, "error": out.split(":", 1)[-1].strip() or out, "ms": ms}
    return {"ok": True, "value": out, "ms": ms}


def dynamic_keys(first):
    """Build per-interface and per-disk keys from discovery results of the first pass."""
    keys = []
    try:
        disks = json.loads(first["perf_instance_en.discovery[PhysicalDisk]"]["value"])
        for d in disks:
            inst = d["{#INSTANCE}"]
            if inst == "_Total":
                continue
            for counter, src in DISK_COUNTERS:
                keys.append(
                    (
                        "disk",
                        f'perf_counter_en["\\PhysicalDisk({inst})\\{counter}",60]',
                        src,
                    )
                )
    except Exception:  # noqa: BLE001
        pass
    try:
        adapters = json.loads(
            next(
                v["value"]
                for k, v in first.items()
                if k.startswith(
                    'wmi.getall[root\\cimv2,"select Name,Description,NetConnectionID'
                )
                and v.get("ok")
            )
        )
        for a in adapters:
            guid = a.get("GUID")
            if guid:
                keys += [
                    ("network", f'net.if.in["{guid}"]', "template"),
                    ("network", f'net.if.out["{guid}"]', "template"),
                    ("network", f'net.if.in["{guid}",errors]', "template"),
                    ("network", f'net.if.out["{guid}",errors]', "template"),
                    ("network", f'net.if.in["{guid}",dropped]', "template"),
                    ("network", f'net.if.out["{guid}",dropped]', "template"),
                    ("network", f'net.if.total["{guid}"]', "extra"),
                ]
            name = a.get("NetConnectionID")
            if name:
                keys.append(("network", f'net.if.in["{name}"]', "extra"))
    except Exception:  # noqa: BLE001
        pass
    return keys


def run_pass(exe, host, port, keys, timeout):
    res = {}
    for _cat, key, _src in keys:
        try:
            res[key] = zabbix_get(exe, host, port, key, timeout)
        except subprocess.TimeoutExpired:
            res[key] = {"ok": False, "error": "zabbix_get timed out", "ms": None}
    return res


def summarize(value):
    """Shorten big JSON/text values for the table; full value stays in the JSON file."""
    v = value.strip()
    if v.startswith("[") or v.startswith("{"):
        try:
            obj = json.loads(v)
            if isinstance(obj, list):
                return f"JSON 배열 {len(obj)}개" + (
                    f" (첫 항목 키: {', '.join(list(obj[0].keys())[:6])})"
                    if obj and isinstance(obj[0], dict)
                    else ""
                )
            return f"JSON 객체 (키: {', '.join(list(obj.keys())[:8])})"
        except ValueError:
            pass
    lines = v.splitlines()
    if len(lines) > 1:
        return f"{len(lines)}줄 텍스트 (첫 줄: {lines[0][:60]})"
    return v if len(v) <= 80 else v[:77] + "..."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zabbix-get", required=True)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=10050)
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=65)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    started = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    first = run_pass(a.zabbix_get, a.host, a.port, STATIC_KEYS, a.timeout)
    keys = STATIC_KEYS + dynamic_keys(first)
    first.update(
        run_pass(a.zabbix_get, a.host, a.port, keys[len(STATIC_KEYS) :], a.timeout)
    )
    time.sleep(a.warmup)
    second = run_pass(a.zabbix_get, a.host, a.port, keys, a.timeout)

    rows = []
    for cat, key, src in keys:
        r2, r1 = second[key], first.get(key, {})
        row = {
            "category": cat,
            "key": key,
            "source": src,
            "ok": r2["ok"],
            "ms": r2["ms"],
            "value": mask(r2.get("value", "")),
            "error": mask(r2.get("error", "")),
            "first_pass": "ok" if r1.get("ok") else mask(r1.get("error", "")),
        }
        rows.append(row)
    meta = {
        "started": started,
        "agent": a.host,
        "port": a.port,
        "warmup_s": a.warmup,
        "keys": len(rows),
        "ok": sum(r["ok"] for r in rows),
    }
    (out / "passive-items.json").write_text(
        json.dumps({"meta": meta, "items": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    md = [
        f"# 패시브 체크 실측 결과 ({started})",
        "",
        f"- 대상: {a.host}:{a.port}, 키 {meta['keys']}개, 성공 {meta['ok']}개, 워밍업 {a.warmup}s 후 2차 측정값",
        "- source: template=공식 Windows 템플릿 사용 키, extra=분석용 추가 확인, expect-unsupported=문서상 Windows 미지원 확인용",
        "",
        "| 분류 | Item key | source | 결과 | 값(요약) / 오류 | 1차 측정 | ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        shown = summarize(r["value"]) if r["ok"] else r["error"]
        shown = shown.replace("|", "\\|").replace("\n", " ")
        md.append(
            f"| {r['category']} | `{r['key'].replace('|', chr(92) + '|')}` | {r['source']} | {'성공' if r['ok'] else '실패'} | {shown} | "
            f"{(r['first_pass'] if r['first_pass'] == 'ok' else '실패: ' + r['first_pass'])[:60].replace('|', chr(92) + '|')} | {r['ms']} |"
        )
    (out / "passive-items.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))


if __name__ == "__main__":
    main()
