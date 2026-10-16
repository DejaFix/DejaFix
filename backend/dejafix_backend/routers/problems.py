"""#6 GET /api/problems?severity_min=&hostid=  (T32, FR-BE-006)

Zabbix 실시간 문제 목록. `problem.get` + `trigger.get(selectHosts)` 를 `dejafix_backend.zabbix`
(타임아웃·짧은 캐시·single-flight)로 거쳐 libs/zabbix_ro 로만 부른다.
- 해결된 문제(r_eventid != 0)는 목록에 없다. 새 문제가 위(clock 내림차순, 같으면 eventid 큰 것 먼저).
- `incident_id`: shared.db 의 `incidents.zabbix_eventid` 와 맞으면 그 장애 id, 아직 수집 전이면 null(shared.db 가 없어도 null).
- 호스트를 알 수 없으면 `host: {id: null, name: null}`(프론트는 UnknownValue 로 표시).
- 최대 MAX_PROBLEMS 건. 더 있으면 `meta.truncated: true`.
- Zabbix 를 못 쓰면 503 `ZABBIX_UNAVAILABLE`(오류 내용·토큰·주소는 응답에 넣지 않는다).
"""

import asyncio
import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from dejafix_backend import zabbix
from dejafix_backend.config import Settings, get_settings
from dejafix_backend.db import open_db
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.errors import ApiError
from dejafix_backend.routers.dashboard import get_now
from dejafix_backend.routers.incidents import SEVERITY_LABELS
from dejafix_backend.timeutil import to_iso

router = APIRouter(tags=["problems"])

MAX_PROBLEMS = 200


def _unavailable() -> ApiError:
    return ApiError(503, "ZABBIX_UNAVAILABLE", "Zabbix에 연결할 수 없습니다")


def _severity(raw: Any) -> dict[str, Any]:
    level = int(raw)
    return {"level": level, "label": SEVERITY_LABELS.get(level, "Not classified")}


def _clock(raw: Any) -> str:
    return to_iso(datetime.fromtimestamp(int(raw), timezone.utc))


async def _collect(
    settings: Settings, severity_min: int | None, hostid: str | None
) -> tuple[list[dict[str, Any]], bool]:
    """(문제 목록, 잘렸는지). Zabbix 가 실패하면 ZabbixUnavailable."""
    params: dict[str, Any] = {
        "output": ["eventid", "objectid", "name", "severity", "clock", "r_eventid"],
        "selectTags": "extend",
        "sortfield": ["eventid"],
        "sortorder": "DESC",
        "limit": MAX_PROBLEMS + 1,  # 하나 더 받아 잘렸는지 안다
    }
    if hostid is not None:
        params["hostids"] = [hostid]
    if severity_min is not None:
        params["severities"] = list(range(severity_min, 6))
    raw = await zabbix.call(settings, "problem.get", params)

    # 해결된 문제는 제외하고, 서버가 걸러 주지 못한 조건은 여기서도 한 번 더 건다
    problems = [p for p in raw if str(p.get("r_eventid", "0")) in ("0", "")]
    if severity_min is not None:
        problems = [p for p in problems if int(p["severity"]) >= severity_min]
    truncated = len(problems) > MAX_PROBLEMS
    problems = problems[:MAX_PROBLEMS]

    hosts_by_trigger: dict[str, dict[str, Any]] = {}
    trigger_ids = sorted({str(p["objectid"]) for p in problems if p.get("objectid")})
    if trigger_ids:
        triggers = await zabbix.call(
            settings,
            "trigger.get",
            {
                "triggerids": trigger_ids,
                "output": ["triggerid"],
                "selectHosts": ["hostid", "host", "name"],
            },
        )
        for trigger in triggers:
            hosts = trigger.get("hosts") or []
            if hosts:
                hosts_by_trigger[str(trigger["triggerid"])] = hosts[0]

    items = []
    for p in problems:
        host = hosts_by_trigger.get(str(p.get("objectid")))
        items.append(
            {
                "eventid": str(p["eventid"]),
                "name": p["name"],
                "severity": _severity(p["severity"]),
                "clock": _clock(p["clock"]),
                "host": {
                    "id": str(host["hostid"]) if host else None,
                    "name": (host.get("name") or host.get("host")) if host else None,
                },
                "tags": [
                    {"tag": str(t["tag"]), "value": str(t.get("value", ""))}
                    for t in p.get("tags") or []
                ],
                "incident_id": None,
            }
        )
    if hostid is not None:  # 서버가 hostids 를 무시해도(목 등) 요청한 호스트만
        items = [i for i in items if i["host"]["id"] == hostid]
    items.sort(key=lambda i: (i["clock"], int(i["eventid"])), reverse=True)
    return items, truncated


def _incident_ids(settings: Settings, eventids: list[str]) -> dict[str, int]:
    """zabbix_eventid → shared.incidents.id. shared.db 가 없거나 읽을 수 없으면 비어 있다(= 전부 null)."""
    if not eventids:
        return {}
    try:
        db = open_db(settings)
    except sqlite3.Error:
        return {}
    try:
        if not db.shared_ok:
            return {}
        marks = ",".join("?" * len(eventids))
        rows = db.conn.execute(
            f"SELECT zabbix_eventid, id FROM shared.incidents WHERE zabbix_eventid IN ({marks})",
            eventids,
        ).fetchall()
        return {str(r["zabbix_eventid"]): int(r["id"]) for r in rows}
    except sqlite3.Error:
        return {}
    finally:
        db.close()


@router.get("/problems")
async def problems(
    severity_min: int | None = Query(None, ge=0, le=5),
    hostid: str | None = None,
    _: dict = Depends(require_role("viewer")),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
):
    try:
        items, truncated = await asyncio.wait_for(
            _collect(settings, severity_min, hostid),
            timeout=settings.zabbix_timeout_sec,
        )
    except (zabbix.ZabbixUnavailable, TimeoutError, KeyError, TypeError, ValueError):
        raise _unavailable() from None
    ids = await run_in_threadpool(
        _incident_ids, settings, [i["eventid"] for i in items]
    )
    for item in items:
        item["incident_id"] = ids.get(item["eventid"])
    return ok(items, collected_at=to_iso(now), truncated=truncated)
