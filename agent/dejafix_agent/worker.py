"""분석 워커·상태 머신 (T48, FR-AG-001·002·014, NFR-PERF-008).

queued → collecting → analyzing → validating → reported → planning → done
- LLM 미설정·실패·타임아웃·초안 검증 실패는 실패가 아니다: fallback 리포트로 계속하고
  done + error(LLM_NOT_CONFIGURED | LLM_TIMEOUT | LLM_ERROR).
- 계획 단계만 실패하면 리포트는 남기고 error 에 PLAN_FAILED.
- 리포트를 하나도 저장하지 못했을 때만 failed.
- 장애당 자동 분석은 1회(caller='worker' run 이 하나라도 있으면 다시 하지 않음).
Agent 가 쓰는 테이블: agent_runs, tool_calls, analysis_reports, change_plans, plan_steps.
incidents 는 읽기만 한다(Scheduler 소유).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from typing import Any

from . import fallback
from .collect import ToolCall, collect, iso, utcnow
from .config import Settings
from .llm import LlmError, complete_json, fake_draft
from .packs import Pack
from .tiers import enforce_plan
from .tools import ToolClient
from .validate import DraftInvalid, Evidence, validate_draft

log = logging.getLogger("dejafix.agent.worker")
INTERVAL_SEC = 10
BATCH = 5


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def pending_incidents(
    conn: sqlite3.Connection, min_severity: int, limit: int = BATCH
) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT i.* FROM incidents i
        WHERE i.severity >= ?
          AND NOT EXISTS (SELECT 1 FROM analysis_reports r WHERE r.incident_id = i.id)
          AND NOT EXISTS (SELECT 1 FROM agent_runs a
                          WHERE a.incident_id = i.id AND a.kind = 'analyze' AND a.caller = 'worker')
        ORDER BY i.started_at, i.id
        LIMIT ?
        """,
        (min_severity, limit),
    ).fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows]


def _set_status(
    conn: sqlite3.Connection, run_id: str, status: str, **fields: Any
) -> None:
    cols = ", ".join(f"{k} = ?" for k in ("status", *fields))
    conn.execute(
        f"UPDATE agent_runs SET {cols} WHERE id = ?", (status, *fields.values(), run_id)
    )
    conn.commit()


def _save_calls(conn: sqlite3.Connection, run_id: str, calls: list[ToolCall]) -> None:
    conn.executemany(
        """INSERT INTO tool_calls(id, run_id, seq, tool, args_json, ok, duration_ms,
               result_summary, result_json, data_clock, called_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                c.id,
                run_id,
                c.seq,
                c.tool,
                _j(c.args),
                int(c.ok),
                c.duration_ms,
                c.summary,
                c.result_json(),
                c.data_clock,
                c.called_at,
            )
            for c in calls
        ],
    )
    conn.execute(
        "UPDATE agent_runs SET tool_call_count = ? WHERE id = ?", (len(calls), run_id)
    )
    conn.commit()


def _save_report(conn, incident_id: int, run_id: str, kind: str, report: dict) -> int:
    version = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM analysis_reports WHERE incident_id = ?",
        (incident_id,),
    ).fetchone()[0]
    cur = conn.execute(
        """INSERT INTO analysis_reports(incident_id, run_id, version, kind, summary, impact_json,
               causes_json, facts_json, unknowns_json, next_checks_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            incident_id,
            run_id,
            version,
            kind,
            report["summary"],
            _j(report["impact"]),
            _j(report["causes"]),
            _j(report["facts"]),
            _j(report["unknowns"]),
            _j(report["next_checks"]),
            iso(utcnow()),
        ),
    )
    conn.commit()
    return cur.lastrowid


def _save_plan(
    conn, incident_id: int, report_id: int, run_id: str, plan: dict, steps: list[dict]
) -> int:
    cur = conn.execute(
        """INSERT INTO change_plans(incident_id, report_id, run_id, title, goal, mode, max_tier,
               assumptions_json, created_at) VALUES (?,?,?,?,?,'preview',?,?,?)""",
        (
            incident_id,
            report_id,
            run_id,
            plan["title"],
            plan["goal"],
            plan["max_tier"],
            _j(plan["assumptions"]),
            iso(utcnow()),
        ),
    )
    plan_id = cur.lastrowid
    conn.executemany(
        """INSERT INTO plan_steps(plan_id, seq, action_id, title, target, command_preview, tier,
               rationale, precheck, expected_effect, risk, rollback, evidence_ids_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [
            (
                plan_id,
                s["seq"],
                s["action_id"],
                s["title"],
                s["target"],
                s["command_preview"],
                s["tier"],
                s["rationale"],
                s["precheck"],
                s["expected_effect"],
                s["risk"],
                s["rollback"],
                _j(s["evidence_ids"]),
            )
            for s in steps
        ],
    )
    conn.commit()
    return plan_id


def run_analysis(
    conn: sqlite3.Connection,
    incident: dict[str, Any],
    settings: Settings,
    pack: Pack,
    client: ToolClient,
    caller: str = "worker",
    requested_by: int | None = None,
) -> str:
    run_id = "r_" + uuid.uuid4().hex[:12]
    conn.execute(
        """INSERT INTO agent_runs(id, kind, incident_id, caller, requested_by, status, model, started_at)
           VALUES (?, 'analyze', ?, ?, ?, 'queued', ?, ?)""",
        (
            run_id,
            incident["id"],
            caller,
            requested_by,
            settings.model_label,
            iso(utcnow()),
        ),
    )
    conn.commit()
    report_id = None
    error: str | None = None
    try:
        _set_status(conn, run_id, "collecting")
        calls = collect(incident, client, pack)
        _save_calls(conn, run_id, calls)
        evidence = {c.id: Evidence(ok=c.ok, stale=c.stale) for c in calls}
        base = fallback.build_draft(incident, calls, pack)

        _set_status(conn, run_id, "analyzing")
        kind, draft = "fallback", base
        mode = settings.llm_mode
        if mode == "fallback":
            error = "LLM_NOT_CONFIGURED"
        else:
            try:
                if mode == "fake":
                    draft = fake_draft(base, [c.id for c in calls if c.ok])
                else:
                    prompt = pack.prompts.get(
                        "analyze", "{allowed_actions}\n{collected}"
                    )
                    prompt = prompt.replace(
                        "{allowed_actions}", pack.allowed_actions_text()
                    ).replace(
                        "{collected}",
                        _j(
                            [
                                {
                                    "id": c.id,
                                    "tool": c.tool,
                                    "ok": c.ok,
                                    "result": c.result,
                                }
                                for c in calls
                            ]
                        ),
                    )
                    draft = complete_json(settings, prompt)
                kind = "llm"
            except LlmError as exc:
                error = exc.code

        _set_status(conn, run_id, "validating")
        try:
            report, plan_draft = validate_draft(draft, evidence)
        except DraftInvalid:
            error = error or "LLM_ERROR"
            kind = "fallback"
            report, plan_draft = validate_draft(base, evidence)

        report_id = _save_report(conn, incident["id"], run_id, kind, report)
        _set_status(conn, run_id, "reported")

        _set_status(conn, run_id, "planning")
        try:
            plan, steps = enforce_plan(plan_draft, pack)
            if plan is None:
                raise ValueError("계획 단계 없음")
            _save_plan(conn, incident["id"], report_id, run_id, plan, steps)
        except Exception as exc:  # 계획 실패는 리포트를 지우지 않는다 (FR-AG-008)
            conn.rollback()
            error = ", ".join(e for e in (error, f"PLAN_FAILED: {exc}") if e)

        _set_status(conn, run_id, "done", error=error, finished_at=iso(utcnow()))
    except Exception as exc:
        conn.rollback()
        log.exception("analysis failed: incident=%s", incident.get("id"))
        status = "done" if report_id else "failed"
        _set_status(
            conn,
            run_id,
            status,
            error=f"{type(exc).__name__}",
            finished_at=iso(utcnow()),
        )
    return run_id


def tick(
    conn: sqlite3.Connection, settings: Settings, pack: Pack, client: ToolClient
) -> list[str]:
    return [
        run_analysis(conn, inc, settings, pack, client)
        for inc in pending_incidents(conn, settings.analyze_min_severity)
    ]


def tick_once(
    db_factory, settings: Settings, pack: Pack, client: ToolClient
) -> list[str]:
    """연결을 열고 한 번 돌고 닫는다. SQLite 연결은 스레드 간에 공유하지 않는다."""
    conn = db_factory()
    try:
        return tick(conn, settings, pack, client)
    finally:
        conn.close()


async def loop(db_factory, settings: Settings, pack: Pack, client: ToolClient) -> None:
    """앱 기동과 함께 도는 10초 주기 워커. 예외로 죽지 않는다."""
    while True:
        try:
            await asyncio.to_thread(tick_once, db_factory, settings, pack, client)
        except Exception:
            log.exception("worker tick failed")
        await asyncio.sleep(INTERVAL_SEC)
