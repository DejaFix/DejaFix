"""Problem 폴링 한 주기 (T36·T37, FR-SCH-001~005·009, NFR-PERF-002).

쓰는 테이블은 Scheduler 소유 두 개뿐: incidents, scheduler_jobs (DB 단일 작성자 원칙, DR-002).
시각은 전부 UTC ISO8601 `YYYY-MM-DDTHH:MM:SSZ` (contracts/incident.schema.json 패턴과 같음).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .source import ProblemSource

log = logging.getLogger("scheduler")

JOB = "poll_problems"
ENRICH_BATCH = 100


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock_iso(value: Any) -> str | None:
    """Zabbix clock(유닉스 초, 문자열로 옴) → UTC ISO. 0·빈 값은 None."""
    try:
        sec = int(value)
    except (TypeError, ValueError):
        return None
    if sec <= 0:
        return None
    return iso(datetime.fromtimestamp(sec, UTC))


def _resolved(problem: dict[str, Any]) -> bool:
    return str(problem.get("r_eventid") or "0") not in ("", "0")


def _tags(problem: dict[str, Any]) -> str:
    tags = [
        {"tag": str(t.get("tag", "")), "value": str(t.get("value", ""))}
        for t in problem.get("tags") or []
        if isinstance(t, dict)
    ]
    return json.dumps(tags, ensure_ascii=False)


@dataclass
class PollResult:
    ok: bool
    seen: int = 0
    inserted: int = 0
    resolved: int = 0
    enriched: int = 0
    message: str | None = None


def _upsert_job(
    conn: sqlite3.Connection, now: str, ok: bool, message: str | None
) -> None:
    conn.execute(
        """INSERT INTO scheduler_jobs(job, last_run_at, last_ok_at, status, message)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(job) DO UPDATE SET
             last_run_at = excluded.last_run_at,
             last_ok_at  = COALESCE(excluded.last_ok_at, scheduler_jobs.last_ok_at),
             status      = excluded.status,
             message     = excluded.message""",
        (JOB, now, now if ok else None, "ok" if ok else "error", message),
    )
    conn.commit()


def _apply_problems(
    conn: sqlite3.Connection,
    problems: list[dict[str, Any]],
    now: str,
    result: PollResult,
) -> None:
    for p in problems:
        eventid = str(p.get("eventid") or "")
        started = clock_iso(p.get("clock"))
        if not eventid or not started:
            continue  # 형식이 틀린 행은 넣지 않는다(지어내지 않음)
        result.seen += 1
        resolved = _resolved(p)
        resolved_at = clock_iso(p.get("r_clock")) if resolved else None
        row = conn.execute(
            "SELECT status FROM incidents WHERE zabbix_eventid = ?", (eventid,)
        ).fetchone()
        if row is None:
            conn.execute(
                """INSERT INTO incidents(zabbix_eventid, zabbix_triggerid, title, severity,
                       status, started_at, resolved_at, acknowledged, tags_json,
                       first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eventid,
                    str(p.get("objectid") or ""),
                    str(p.get("name") or ""),
                    min(5, max(0, int(p.get("severity") or 0))),
                    "resolved" if resolved else "problem",
                    started,
                    resolved_at,
                    1 if str(p.get("acknowledged") or "0") == "1" else 0,
                    _tags(p),
                    now,
                    now,
                ),
            )
            result.inserted += 1
            if resolved:
                result.resolved += 1
            continue
        if resolved and row[0] == "problem":
            conn.execute(
                """UPDATE incidents SET status='resolved', resolved_at=?, last_seen_at=?
                   WHERE zabbix_eventid=?""",
                (resolved_at or now, now, eventid),
            )
            result.resolved += 1
        else:
            conn.execute(
                "UPDATE incidents SET last_seen_at=? WHERE zabbix_eventid=?",
                (now, eventid),
            )


def _enrich_hosts(
    conn: sqlite3.Connection, source: ProblemSource, result: PollResult
) -> None:
    rows = conn.execute(
        """SELECT DISTINCT zabbix_triggerid FROM incidents
           WHERE (hostid IS NULL OR host_name IS NULL) AND zabbix_triggerid <> ''
           LIMIT ?""",
        (ENRICH_BATCH,),
    ).fetchall()
    triggerids = [r[0] for r in rows]
    if not triggerids:
        return
    hosts = source.trigger_hosts(triggerids)
    for triggerid, host in hosts.items():
        cur = conn.execute(
            """UPDATE incidents SET hostid=?, host_name=?
               WHERE zabbix_triggerid=? AND (hostid IS NULL OR host_name IS NULL)""",
            (host.get("hostid") or None, host.get("name") or None, triggerid),
        )
        result.enriched += cur.rowcount


def poll_once(
    conn: sqlite3.Connection, source: ProblemSource, now: datetime | None = None
) -> PollResult:
    """한 주기. 예외로 죽지 않고 결과를 scheduler_jobs 에 남긴다 (FR-SCH-004)."""
    stamp = iso(now or utcnow())
    result = PollResult(ok=True)
    try:
        problems = source.problems()
        _apply_problems(conn, problems, stamp, result)
        conn.commit()  # 새 장애는 호스트 보강이 실패해도 남긴다
        # 같은 주기 안에 호스트를 채운다. 실패하면 다음 주기에 hostid 가 빈 행을 다시 시도.
        _enrich_hosts(conn, source, result)
        conn.commit()
    except Exception as exc:  # 다음 주기 재시도
        conn.rollback()
        result.ok = False
        result.message = f"{type(exc).__name__}: {str(exc)[:200]}"
        log.error("poll_problems 실패: %s", result.message)
    _upsert_job(conn, stamp, result.ok, result.message)
    if result.ok:
        log.info(
            "poll_problems ok seen=%d inserted=%d resolved=%d enriched=%d",
            result.seen,
            result.inserted,
            result.resolved,
            result.enriched,
        )
    return result
