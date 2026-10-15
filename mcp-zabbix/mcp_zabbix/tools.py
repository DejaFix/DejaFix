"""필수 조회 도구 5개 (contracts/mcp-tools.md 3장, FR-MCP-002~006).

함수마다 zabbix_ro 클라이언트를 받아 공통 봉투를 돌려준다. Zabbix 호출은 전부 libs/zabbix_ro 경유(SAFE-02).
아이템 키는 고르지 않는다(키 선택은 packs/<pack>/metrics.yaml, 엔진 하드코딩 금지).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Protocol

from .envelope import (
    MAX_LIST,
    MAX_POINTS,
    fail,
    from_error,
    is_stale,
    ok,
    parse_time,
)

DAY = 86400


class Client(Protocol):
    def call(self, method: str, params: dict[str, Any] | None = None) -> Any: ...


def _guard(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """예외를 실패 봉투로 바꾼다. 인자 오류는 ZABBIX_ERROR + 한 줄 사유."""

    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            return fail("ZABBIX_ERROR", f"인자 오류: {exc}"[:120])
        except Exception as exc:  # noqa: BLE001 — 스택을 LLM에 넘기지 않는다
            return from_error(exc)

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _limit(value: Any, maximum: int) -> int:
    if value is None or value == "":
        return maximum
    n = int(value)
    if n < 1:
        raise ValueError("limit 은 1 이상")
    return min(n, maximum)


def _tags(rows: Any) -> list[dict[str, str]]:
    return [
        {"tag": str(t.get("tag", "")), "value": str(t.get("value", ""))}
        for t in rows or []
    ]


def _hosts(rows: Any) -> list[dict[str, str]]:
    return [
        {"hostid": str(h.get("hostid", "")), "name": str(h.get("name", ""))}
        for h in rows or []
    ]


def _items(rows: Any) -> list[dict[str, str]]:
    keys = ("itemid", "key_", "name", "value_type", "units")
    return [{k: str(i.get(k, "")) for k in keys} for i in rows or []]


@_guard
def list_problems(
    client: Client,
    severity_min: int | None = None,
    hostid: str | None = None,
    since: Any = None,
    limit: int | None = None,
) -> dict[str, Any]:
    sev = int(severity_min or 0)
    if not 0 <= sev <= 5:
        raise ValueError("severity_min 은 0~5")
    lim = _limit(limit, MAX_LIST)
    params: dict[str, Any] = {
        "output": ["eventid", "objectid", "name", "severity", "clock"],
        "recent": True,
        "severities": list(range(sev, 6)),
        "selectTags": "extend",
        "sortfield": ["eventid"],
        "sortorder": "DESC",
        "limit": lim + 1,
    }
    if hostid:
        params["hostids"] = [str(hostid)]
    t_from = parse_time(since)
    if t_from is not None:
        params["time_from"] = t_from
    problems = client.call("problem.get", params) or []
    truncated = len(problems) > lim
    problems = problems[:lim]

    host_of: dict[str, dict[str, str]] = {}
    trigger_ids = sorted(
        {str(p.get("objectid")) for p in problems if p.get("objectid")}
    )
    if trigger_ids:
        triggers = client.call(
            "trigger.get",
            {
                "triggerids": trigger_ids,
                "output": ["triggerid"],
                "selectHosts": ["hostid", "name"],
            },
        )
        for t in triggers or []:
            hosts = _hosts(t.get("hosts"))
            if hosts:
                host_of[str(t.get("triggerid"))] = hosts[0]

    data = [
        {
            "eventid": str(p.get("eventid", "")),
            "objectid": str(p.get("objectid", "")),
            "name": str(p.get("name", "")),
            "severity": str(p.get("severity", "")),
            "clock": str(p.get("clock", "")),
            "host": host_of.get(str(p.get("objectid")), {"hostid": "", "name": ""}),
            "tags": _tags(p.get("tags")),
        }
        for p in problems
    ]
    return ok(data, truncated)


@_guard
def get_problem(client: Client, eventid: str) -> dict[str, Any]:
    if not eventid:
        raise ValueError("eventid 필요")
    events = client.call(
        "event.get",
        {
            "eventids": [str(eventid)],
            "output": "extend",
            "selectHosts": ["hostid", "name"],
            "selectTags": "extend",
            "select_acknowledges": ["clock", "message", "action"],
        },
    )
    events = [e for e in events or [] if str(e.get("eventid")) == str(eventid)]
    if not events:
        return fail("NOT_FOUND", "장애를 찾을 수 없음")
    ev = events[0]

    r_clock = str(ev.get("r_clock") or "0")
    r_eventid = str(ev.get("r_eventid") or "0")
    if r_clock == "0" and r_eventid != "0":
        rec = client.call("event.get", {"eventids": [r_eventid], "output": ["clock"]})
        rec = [r for r in rec or [] if str(r.get("eventid", r_eventid)) == r_eventid]
        if rec:
            r_clock = str(rec[0].get("clock", "0"))

    trigger: dict[str, Any] = {
        "triggerid": str(ev.get("objectid", "")),
        "description": "",
        "expression": "",
        "items": [],
    }
    if ev.get("objectid"):
        triggers = client.call(
            "trigger.get",
            {
                "triggerids": [str(ev["objectid"])],
                "output": ["triggerid", "description", "expression"],
                "expandDescription": True,
                "expandExpression": True,
                "selectItems": ["itemid", "key_", "name", "value_type", "units"],
                "selectFunctions": "extend",
            },
        )
        triggers = [
            t for t in triggers or [] if str(t.get("triggerid")) == str(ev["objectid"])
        ]
        if triggers:
            t = triggers[0]
            trigger = {
                "triggerid": str(t.get("triggerid", "")),
                "description": str(t.get("description", "")),
                "expression": str(t.get("expression", "")),
                "items": _items(t.get("items")),
            }

    data = {
        "eventid": str(ev.get("eventid", "")),
        "name": str(ev.get("name", "")),
        "severity": str(ev.get("severity", "")),
        "clock": str(ev.get("clock", "")),
        "r_clock": r_clock,
        "acknowledged": str(ev.get("acknowledged", "0")),
        "hosts": _hosts(ev.get("hosts")),
        "tags": _tags(ev.get("tags")),
        "trigger": trigger,
        "items": list(trigger["items"]),
    }
    return ok(data)


@_guard
def get_host(client: Client, hostid: str) -> dict[str, Any]:
    if not hostid:
        raise ValueError("hostid 필요")
    hosts = client.call(
        "host.get",
        {
            "hostids": [str(hostid)],
            "output": [
                "hostid",
                "host",
                "name",
                "status",
                "active_available",
                "maintenance_status",
            ],
            "selectHostGroups": ["groupid", "name"],
        },
    )
    hosts = [h for h in hosts or [] if str(h.get("hostid")) == str(hostid)]
    if not hosts:
        return fail("NOT_FOUND", "호스트를 찾을 수 없음")
    h = hosts[0]
    # ip·dns 는 받지도 넘기지도 않는다 (계약 2-3)
    interfaces = client.call(
        "hostinterface.get",
        {"hostids": [str(hostid)], "output": ["type", "main", "available", "error"]},
    )
    data = {
        "hostid": str(h.get("hostid", "")),
        "host": str(h.get("host", "")),
        "name": str(h.get("name", "")),
        "available": str(h.get("active_available", "0")),
        "interfaces": [
            {k: str(i.get(k, "")) for k in ("type", "main", "available", "error")}
            for i in interfaces or []
        ],
        "groups": [
            {"groupid": str(g.get("groupid", "")), "name": str(g.get("name", ""))}
            for g in h.get("hostgroups") or h.get("groups") or []
        ],
        "in_maintenance": str(h.get("maintenance_status", "0")) == "1",
    }
    return ok(data)


@_guard
def list_items(
    client: Client, hostid: str, key_search: str | None = None
) -> dict[str, Any]:
    if not hostid:
        raise ValueError("hostid 필요")
    params: dict[str, Any] = {
        "hostids": [str(hostid)],
        "output": [
            "itemid",
            "name",
            "key_",
            "lastvalue",
            "lastclock",
            "units",
            "delay",
            "value_type",
            "state",
        ],
        "filter": {"status": "0"},
        "sortfield": "key_",
        "limit": MAX_LIST + 1,
    }
    if key_search:
        params["search"] = {"key_": str(key_search)}
    items = client.call("item.get", params) or []
    truncated = len(items) > MAX_LIST
    keys = (
        "itemid",
        "name",
        "key_",
        "lastvalue",
        "lastclock",
        "units",
        "delay",
        "value_type",
        "state",
    )
    data = []
    for i in items[:MAX_LIST]:
        row = {k: str(i.get(k, "")) for k in keys}
        row["stale"] = is_stale(i.get("lastclock"), i.get("delay"))
        data.append(row)
    return ok(data, truncated)


@_guard
def get_history(
    client: Client,
    itemid: str,
    time_from: Any,
    time_till: Any = None,
    limit: int | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    if not itemid:
        raise ValueError("itemid 필요")
    t_from = parse_time(time_from)
    if t_from is None:
        raise ValueError("time_from 필요")
    t_till = parse_time(time_till, int(time.time() if now is None else now))
    if t_till < t_from:
        raise ValueError("time_till 이 time_from 보다 이름")
    lim = _limit(limit, MAX_POINTS)

    items = client.call(
        "item.get",
        {
            "itemids": [str(itemid)],
            "output": ["itemid", "value_type", "delay", "lastclock"],
        },
    )
    items = [i for i in items or [] if str(i.get("itemid")) == str(itemid)]
    if not items:
        return fail("NOT_FOUND", "지표 항목을 찾을 수 없음")
    item = items[0]
    vtype = int(str(item.get("value_type", "3")))

    if t_till - t_from > DAY and vtype in (0, 3):
        source = "trend"
        rows = client.call(
            "trend.get",
            {
                "itemids": [str(itemid)],
                "time_from": t_from,
                "time_till": t_till,
                "output": ["itemid", "clock", "value_avg"],
                "limit": lim + 1,
            },
        )
        rows = [r for r in rows or [] if str(r.get("itemid", itemid)) == str(itemid)]
        rows.sort(key=lambda r: int(str(r.get("clock", "0"))), reverse=True)
        points = [
            {"clock": str(r.get("clock", "")), "value": str(r.get("value_avg", ""))}
            for r in rows
        ]
    else:
        source = "history"
        rows = client.call(
            "history.get",
            {
                "history": vtype,
                "itemids": [str(itemid)],
                "time_from": t_from,
                "time_till": t_till,
                "output": "extend",
                "sortfield": "clock",
                "sortorder": "DESC",
                "limit": lim + 1,
            },
        )
        rows = [r for r in rows or [] if str(r.get("itemid", itemid)) == str(itemid)]
        rows.sort(key=lambda r: int(str(r.get("clock", "0"))), reverse=True)
        points = [
            {"clock": str(r.get("clock", "")), "value": str(r.get("value", ""))}
            for r in rows
        ]

    truncated = len(points) > lim
    points = list(reversed(points[:lim]))  # 최근 lim 개를 시간순으로
    last_clock = points[-1]["clock"] if points else str(item.get("lastclock", "0"))
    data = {
        "itemid": str(itemid),
        "source": source,
        "points": points,
        "last_clock": last_clock,
        "stale": is_stale(last_clock, item.get("delay"), now),
    }
    return ok(data, truncated)
