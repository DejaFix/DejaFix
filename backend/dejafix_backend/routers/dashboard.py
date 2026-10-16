"""#5 GET /api/dashboard/summary  (T32, FR-BE-005)

KPI 4종, 모든 값이 `Measured`(계약 api.md API 5번). 두 곳에서 따로 계산한다.
- shared.db 집계(활성 장애·High 이상·오늘 리포트·평균 분석 시간): Zabbix 가 끊겨도 값을 유지한다.
- Zabbix 호스트 집계(감시 호스트 total·정상 ok·확인 불가 unknown): Zabbix 를 못 쓰면 `unknown:true, unknown_reason:"TOOL_ERROR"`.
  Zabbix 는 `dejafix_backend.zabbix`(타임아웃·짧은 캐시·single-flight)를 거쳐 libs/zabbix_ro 로만 부른다.
"오늘" = KST 자정 기준. 시각은 UTC `YYYY-MM-DDTHH:MM:SSZ`.
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from dejafix_backend import zabbix
from dejafix_backend.config import Settings, get_settings
from dejafix_backend.db import open_db
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.timeutil import to_iso

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

KST = timezone(timedelta(hours=9))
HIGH_SEVERITY = 4  # High(4)·Disaster(5)


def get_now() -> datetime:
    """테스트에서 시각을 고정하는 자리."""
    return datetime.now(timezone.utc)


def measured(value: int | float, unit: str, collected_at: str) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "collected_at": collected_at,
        "unknown": False,
    }


def unknown(unit: str, collected_at: str, reason: str) -> dict[str, Any]:
    """확인할 수 없는 값은 0·빈 칸이 아니라 value=null + 사유 (SAFE-10)."""
    return {
        "value": None,
        "unit": unit,
        "collected_at": collected_at,
        "unknown": True,
        "unknown_reason": reason,
    }


def kst_today_window(now: datetime) -> tuple[str, str]:
    """KST 오늘 00:00 ~ 내일 00:00 을 UTC ISO 문자열 [시작, 끝) 으로."""
    midnight_kst = now.astimezone(KST).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return to_iso(midnight_kst), to_iso(midnight_kst + timedelta(days=1))


# ---------------------------------------------------------------- shared.db 집계


_SHARED_UNITS = {
    "active_incidents": "건",
    "high_incidents": "건",
    "reports_today": "건",
    "avg_analysis_sec": "s",
}


def _shared_kpis(settings: Settings, now: datetime) -> dict[str, dict[str, Any]]:
    collected = to_iso(now)
    missing = {k: unknown(u, collected, "NO_DATA") for k, u in _SHARED_UNITS.items()}
    try:
        db = open_db(settings)
    except sqlite3.Error:
        return missing
    try:
        if not db.shared_ok:  # Agent·Scheduler 가 아직 shared.db 를 만들기 전
            return missing
        start, end = kst_today_window(now)
        conn = db.conn
        active = conn.execute(
            "SELECT COUNT(*) FROM shared.incidents WHERE status = 'problem'"
        ).fetchone()[0]
        high = conn.execute(
            "SELECT COUNT(*) FROM shared.incidents"
            " WHERE status = 'problem' AND severity >= ?",
            (HIGH_SEVERITY,),
        ).fetchone()[0]
        reports = conn.execute(
            "SELECT COUNT(*) FROM shared.analysis_reports"
            " WHERE created_at >= ? AND created_at < ?",
            (start, end),
        ).fetchone()[0]
        avg = conn.execute(
            "SELECT AVG((julianday(finished_at) - julianday(started_at)) * 86400.0)"
            " FROM shared.agent_runs"
            " WHERE kind = 'analyze' AND finished_at IS NOT NULL"
            " AND started_at >= ? AND started_at < ?",
            (start, end),
        ).fetchone()[0]
    except sqlite3.Error:
        return missing
    finally:
        db.close()
    return {
        "active_incidents": measured(active, "건", collected),
        "high_incidents": measured(high, "건", collected),
        "reports_today": measured(reports, "건", collected),
        # 오늘 끝난 분석 run 이 없으면 평균을 0 으로 그리지 않고 "확인할 수 없음"
        "avg_analysis_sec": measured(round(avg, 1), "s", collected)
        if avg is not None
        else unknown("s", collected, "NO_DATA"),
    }


# ---------------------------------------------------------------- Zabbix 호스트 집계


async def _collect_hosts(settings: Settings) -> tuple[int, int, int]:
    """(total, ok, unknown). Zabbix 가 실패하면 ZabbixUnavailable."""
    hosts, problems = await asyncio.gather(
        zabbix.call(
            settings,
            "host.get",
            {
                "output": ["hostid", "status", "active_available"],
                "filter": {"status": "0"},
            },
        ),
        zabbix.call(
            settings, "problem.get", {"output": ["eventid", "objectid", "r_eventid"]}
        ),
    )
    # 해결된 문제(r_eventid != 0)는 활성이 아니다
    active = [p for p in problems if str(p.get("r_eventid", "0")) in ("0", "")]
    trigger_ids = sorted({str(p["objectid"]) for p in active if p.get("objectid")})
    hosts_with_problem: set[str] = set()
    if trigger_ids:
        triggers = await zabbix.call(
            settings,
            "trigger.get",
            {
                "triggerids": trigger_ids,
                "output": ["triggerid"],
                "selectHosts": ["hostid"],
            },
        )
        for trigger in triggers:
            for host in trigger.get("hosts") or []:
                hosts_with_problem.add(str(host["hostid"]))

    monitored = [h for h in hosts if str(h.get("status", "0")) == "0"]
    total = len(monitored)
    # 가용성: 0 알 수 없음 · 1 사용 가능 · 2 사용 불가 (불가는 total 에만 들어간다)
    unknown_count = sum(
        1 for h in monitored if str(h.get("active_available", "0")) == "0"
    )
    ok_count = sum(
        1
        for h in monitored
        if str(h.get("active_available")) == "1"
        and str(h["hostid"]) not in hosts_with_problem
    )
    return total, ok_count, unknown_count


async def _host_kpis(settings: Settings, now: datetime) -> dict[str, dict[str, Any]]:
    collected = to_iso(now)
    try:
        # 여러 호출이 겹쳐도 전체가 한도 안에 끝나게 묶는다.
        # 시간이 지나도 이미 나간 Zabbix 요청은 계속 돌아 캐시를 채운다(zabbix.call 의 shield).
        total, ok_count, unknown_count = await asyncio.wait_for(
            _collect_hosts(settings), timeout=settings.zabbix_timeout_sec
        )
    except (zabbix.ZabbixUnavailable, TimeoutError, KeyError, TypeError, ValueError):
        return {
            name: unknown("대", collected, "TOOL_ERROR")
            for name in ("ok", "total", "unknown")
        }
    return {
        "ok": measured(ok_count, "대", collected),
        "total": measured(total, "대", collected),
        "unknown": measured(unknown_count, "대", collected),
    }


@router.get("/summary")
async def summary(
    _: dict = Depends(require_role("viewer")),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
):
    shared, hosts = await asyncio.gather(
        run_in_threadpool(_shared_kpis, settings, now),
        _host_kpis(settings, now),
    )
    data = {
        "active_incidents": shared["active_incidents"],
        "high_incidents": shared["high_incidents"],
        "hosts": hosts,
        "reports_today": shared["reports_today"],
        "avg_analysis_sec": shared["avg_analysis_sec"],
        "llm_usage_today": None,  # [선택] — 필수 단계에서는 null
    }
    return ok(data, generated_at=to_iso(now))
