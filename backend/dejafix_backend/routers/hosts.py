"""#7 GET /api/hosts  (계약 contracts/api.md #7)

Zabbix 감시 중(`status=0`) 호스트마다 에이전트 연결 상태와 열린 Problem 수.
`host.get`·`problem.get`·`trigger.get` 를 `dejafix_backend.zabbix`(타임아웃·짧은 캐시·single-flight)로
거쳐 libs/zabbix_ro 로만 부른다.
- state: 에이전트 가용성(`active_available`, 에이전트 인터페이스 `available`) 중 1 이 있으면 up,
  1 은 없고 2 가 있으면 down, 그 밖은 unknown. 장애가 없다고 up 으로 보지 않는다(SAFE-08·09).
- problems: 해결되지 않은 Problem 수. state 는 바꾸지 않는다(연결과 장애는 따로 본다).
- 이름순, 최대 MAX_HOSTS 대. 더 있으면 `meta.truncated: true`.
- Zabbix 를 못 쓰면 503 `ZABBIX_UNAVAILABLE`(#6 과 같다).
"""

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends

from dejafix_backend import zabbix
from dejafix_backend.config import Settings, get_settings
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.errors import ApiError
from dejafix_backend.routers.dashboard import get_now
from dejafix_backend.timeutil import to_iso

router = APIRouter(tags=["hosts"])

MAX_HOSTS = 500
AGENT_INTERFACE = "1"  # Zabbix 인터페이스 type 1 = 에이전트


def _unavailable() -> ApiError:
    return ApiError(503, "ZABBIX_UNAVAILABLE", "Zabbix에 연결할 수 없습니다")


def state_of(host: dict[str, Any]) -> str:
    """에이전트 가용성으로만 정한다. 0·값 없음은 unknown."""
    marks = [str(host.get("active_available", "0"))]
    for iface in host.get("interfaces") or []:
        if str(iface.get("type")) == AGENT_INTERFACE:
            marks.append(str(iface.get("available", "0")))
    if "1" in marks:
        return "up"
    if "2" in marks:
        return "down"
    return "unknown"


async def _problem_counts(settings: Settings) -> dict[str, int]:
    """hostid → 해결되지 않은 Problem 수."""
    problems = await zabbix.call(
        settings, "problem.get", {"output": ["eventid", "objectid", "r_eventid"]}
    )
    active = [p for p in problems if str(p.get("r_eventid", "0")) in ("0", "")]
    per_trigger: dict[str, int] = {}
    for p in active:
        if p.get("objectid"):
            key = str(p["objectid"])
            per_trigger[key] = per_trigger.get(key, 0) + 1
    if not per_trigger:
        return {}
    triggers = await zabbix.call(
        settings,
        "trigger.get",
        {
            "triggerids": sorted(per_trigger),
            "output": ["triggerid"],
            "selectHosts": ["hostid"],
        },
    )
    counts: dict[str, int] = {}
    for trigger in triggers:
        n = per_trigger.get(str(trigger["triggerid"]), 0)
        for host in trigger.get("hosts") or []:
            hid = str(host["hostid"])
            counts[hid] = counts.get(hid, 0) + n
    return counts


async def _collect(settings: Settings) -> tuple[list[dict[str, Any]], bool]:
    """(호스트 목록, 잘렸는지). Zabbix 가 실패하면 ZabbixUnavailable."""
    hosts, counts = await asyncio.gather(
        zabbix.call(
            settings,
            "host.get",
            {
                "output": ["hostid", "host", "name", "status", "active_available"],
                "filter": {"status": "0"},
                "selectInterfaces": ["type", "available"],
            },
        ),
        _problem_counts(settings),
    )
    rows = [
        {
            "id": str(h["hostid"]),
            "name": h.get("name") or h.get("host") or str(h["hostid"]),
            "state": state_of(h),
            "problems": counts.get(str(h["hostid"]), 0),
        }
        for h in hosts
        if str(h.get("status", "0")) == "0"
    ]
    rows.sort(key=lambda r: (r["name"].lower(), r["id"]))
    return rows[:MAX_HOSTS], len(rows) > MAX_HOSTS


@router.get("/hosts")
async def hosts(
    _: dict = Depends(require_role("viewer")),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
):
    try:
        rows, truncated = await asyncio.wait_for(
            _collect(settings), timeout=settings.zabbix_timeout_sec
        )
    except (zabbix.ZabbixUnavailable, TimeoutError, KeyError, TypeError, ValueError):
        raise _unavailable() from None
    return ok(rows, collected_at=to_iso(now), truncated=truncated)
