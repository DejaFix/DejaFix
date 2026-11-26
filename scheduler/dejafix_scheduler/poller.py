"""Problem 폴링 한 주기 (T36·T37, FR-SCH-001~005·009, NFR-PERF-002).

쓰는 테이블은 Scheduler 소유 두 개뿐: incidents, scheduler_jobs (DB 단일 작성자 원칙, DR-002).
시각은 전부 UTC ISO8601 `YYYY-MM-DDTHH:MM:SSZ` (contracts/incident.schema.json 패턴과 같음).

회사별(결정 019): `Scope(company, conn_id)` 를 넘기면 그 회사 행만 읽고 쓴다(company_id·zabbix_conn_id 를
늘 직접 넣는다, db-schema.sql 규칙 8). 연결이 바뀌었으면 폴링 전에 그 회사의 옛 연결 열린 장애를
`connection_changed` 로 닫는다. Scope 가 없으면(회사 나누기 꺼짐) 지금 그대로.
"""

from __future__ import annotations

import json
import logging
import os
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


@dataclass(frozen=True)
class Scope:
    """폴링 한 번의 회사와 그 회사 지금 Zabbix 연결 구분값 (결정 019)."""

    company: str
    conn_id: str


@dataclass
class PollResult:
    ok: bool
    seen: int = 0
    inserted: int = 0
    resolved: int = 0
    enriched: int = 0
    message: str | None = None
    closed: int = 0


def _jobs_have_company(conn: sqlite3.Connection) -> bool:
    return any(
        row[1] == "company_id"
        for row in conn.execute("PRAGMA table_info(scheduler_jobs)")
    )


def upsert_job(
    conn: sqlite3.Connection,
    job: str,
    now: str,
    ok: bool,
    message: str | None,
    company: str | None = None,
) -> None:
    """scheduler_jobs 의 job 행 1개 UPSERT. 실패면 last_ok_at 은 그대로 둔다.

    019 이관 뒤에는 회사별 행이다. company 가 없으면(설치 전체 작업 kb_reindex·kb_notes) 기본 회사 행.
    """
    if _jobs_have_company(conn):
        company = company or (os.environ.get("DEFAULT_COMPANY_ID") or "").strip()
        if not company:
            raise ValueError("scheduler_jobs 에 회사가 필요합니다 (DEFAULT_COMPANY_ID)")
        conn.execute(
            """INSERT INTO scheduler_jobs(company_id, job, last_run_at, last_ok_at, status, message)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(company_id, job) DO UPDATE SET
                 last_run_at = excluded.last_run_at,
                 last_ok_at  = COALESCE(excluded.last_ok_at, scheduler_jobs.last_ok_at),
                 status      = excluded.status,
                 message     = excluded.message""",
            (company, job, now, now if ok else None, "ok" if ok else "error", message),
        )
        conn.commit()
        return
    conn.execute(
        """INSERT INTO scheduler_jobs(job, last_run_at, last_ok_at, status, message)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(job) DO UPDATE SET
             last_run_at = excluded.last_run_at,
             last_ok_at  = COALESCE(excluded.last_ok_at, scheduler_jobs.last_ok_at),
             status      = excluded.status,
             message     = excluded.message""",
        (job, now, now if ok else None, "ok" if ok else "error", message),
    )
    conn.commit()


def _apply_problems(
    conn: sqlite3.Connection,
    problems: list[dict[str, Any]],
    now: str,
    result: PollResult,
    scope: Scope | None = None,
) -> None:
    # 회사별이면 (회사, 연결 구분값, eventid) 로 가른다(db-schema.sql 규칙 8)
    where = "zabbix_eventid = ?"
    if scope is not None:
        where += " AND company_id = ? AND zabbix_conn_id = ?"
    for p in problems:
        eventid = str(p.get("eventid") or "")
        started = clock_iso(p.get("clock"))
        if not eventid or not started:
            continue  # 형식이 틀린 행은 넣지 않는다(지어내지 않음)
        key = (eventid,) if scope is None else (eventid, scope.company, scope.conn_id)
        result.seen += 1
        resolved = _resolved(p)
        resolved_at = clock_iso(p.get("r_clock")) if resolved else None
        row = conn.execute(
            f"SELECT status FROM incidents WHERE {where}", key
        ).fetchone()
        if row is None:
            values = (
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
            )
            if scope is None:
                conn.execute(
                    """INSERT INTO incidents(zabbix_eventid, zabbix_triggerid, title, severity,
                           status, started_at, resolved_at, acknowledged, tags_json,
                           first_seen_at, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
            else:
                conn.execute(
                    """INSERT INTO incidents(zabbix_eventid, zabbix_triggerid, title, severity,
                           status, started_at, resolved_at, acknowledged, tags_json,
                           first_seen_at, last_seen_at, company_id, zabbix_conn_id, resolved_reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        *values,
                        scope.company,
                        scope.conn_id,
                        "zabbix" if resolved else None,
                    ),
                )
            result.inserted += 1
            if resolved:
                result.resolved += 1
            continue
        if resolved and row[0] == "problem":
            reason = "" if scope is None else ", resolved_reason='zabbix'"
            conn.execute(
                f"""UPDATE incidents SET status='resolved', resolved_at=?, last_seen_at=?{reason}
                   WHERE {where}""",
                (resolved_at or now, now, *key),
            )
            result.resolved += 1
        else:
            conn.execute(
                f"UPDATE incidents SET last_seen_at=? WHERE {where}",
                (now, *key),
            )


def close_changed_connection(conn: sqlite3.Connection, scope: Scope, now: str) -> int:
    """그 회사의 지금 연결이 아닌 연결에서 온 열린 장애를 닫는다(connection_changed). 행은 지우지 않는다."""
    cur = conn.execute(
        """UPDATE incidents SET status='resolved', resolved_at=?, resolved_reason='connection_changed'
           WHERE company_id=? AND zabbix_conn_id<>? AND status='problem'""",
        (now, scope.company, scope.conn_id),
    )
    return cur.rowcount


def _enrich_hosts(
    conn: sqlite3.Connection,
    source: ProblemSource,
    result: PollResult,
    scope: Scope | None = None,
) -> None:
    # 회사별이면 그 회사·그 연결 행만 그 연결의 Zabbix 로 보강한다(다른 회사 triggerid 를 묻지 않는다)
    extra, args = "", ()
    if scope is not None:
        extra, args = (
            " AND company_id=? AND zabbix_conn_id=?",
            (scope.company, scope.conn_id),
        )
    rows = conn.execute(
        f"""SELECT DISTINCT zabbix_triggerid FROM incidents
           WHERE (hostid IS NULL OR host_name IS NULL) AND zabbix_triggerid <> ''{extra}
           LIMIT ?""",
        (*args, ENRICH_BATCH),
    ).fetchall()
    triggerids = [r[0] for r in rows]
    if not triggerids:
        return
    hosts = source.trigger_hosts(triggerids)
    for triggerid, host in hosts.items():
        cur = conn.execute(
            f"""UPDATE incidents SET hostid=?, host_name=?
               WHERE zabbix_triggerid=? AND (hostid IS NULL OR host_name IS NULL){extra}""",
            (host.get("hostid") or None, host.get("name") or None, triggerid, *args),
        )
        result.enriched += cur.rowcount


def poll_once(
    conn: sqlite3.Connection,
    source: ProblemSource,
    now: datetime | None = None,
    scope: Scope | None = None,
) -> PollResult:
    """한 주기. 예외로 죽지 않고 결과를 scheduler_jobs 에 남긴다 (FR-SCH-004).

    scope 가 있으면 그 회사 몫만(결정 019). 연결이 바뀌었으면 폴링 전에 옛 연결 열린 장애를 닫는다.
    """
    stamp = iso(now or utcnow())
    result = PollResult(ok=True)
    try:
        if scope is not None:
            result.closed = close_changed_connection(conn, scope, stamp)
            conn.commit()  # Zabbix 조회가 실패해도 옛 연결 장애는 닫는다
        problems = source.problems()
        _apply_problems(conn, problems, stamp, result, scope)
        conn.commit()  # 새 장애는 호스트 보강이 실패해도 남긴다
        # 같은 주기 안에 호스트를 채운다. 실패하면 다음 주기에 hostid 가 빈 행을 다시 시도.
        _enrich_hosts(conn, source, result, scope)
        conn.commit()
    except Exception as exc:  # 다음 주기 재시도
        conn.rollback()
        result.ok = False
        result.message = f"{type(exc).__name__}: {str(exc)[:200]}"
        log.error("poll_problems 실패: %s", result.message)
    upsert_job(
        conn, JOB, stamp, result.ok, result.message, scope.company if scope else None
    )
    if result.ok:
        log.info(
            "poll_problems ok company=%s seen=%d inserted=%d resolved=%d enriched=%d closed=%d",
            scope.company if scope else "-",
            result.seen,
            result.inserted,
            result.resolved,
            result.enriched,
            result.closed,
        )
    return result
