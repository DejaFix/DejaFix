"""#10 GET /api/incidents, #11 GET /api/incidents/{id}  (T33)

shared.db(읽기 전용 ATTACH)와 backend.db(mail_logs)에서 읽기만 한다. 분석 문장·원인·티어를 만들거나 바꾸지 않고
Agent 가 저장한 값을 그대로 옮긴다. 응답에 execute/run 필드는 없고 plan.mode 는 항상 "preview" 다 (SAFE-04).
analysis.status 변환은 contracts/agent-api.md 3-2 절 표를 따른다.
"""

import json
import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from dejafix_backend.config import Settings, get_settings
from dejafix_backend.db import Db
from dejafix_backend.deps import get_db, require_role
from dejafix_backend.envelope import decode_cursor, encode_cursor, ok
from dejafix_backend.errors import ApiError

router = APIRouter(prefix="/incidents", tags=["incidents"])

SEVERITY_LABELS = {
    0: "Not classified",
    1: "Information",
    2: "Warning",
    3: "Average",
    4: "High",
    5: "Disaster",
}

# agent_runs.status 중 아직 진행 중인 값 (done·failed 가 아닌 것)
_RUNNING = {"queued", "collecting", "analyzing", "validating", "reported", "planning"}

# 장애마다 가장 최근 analyze run, 최신 version 리포트, 그 리포트의 계획을 서브쿼리로 붙인다.
# 계획 선택(contracts/api.md API 11번): change_plans.report_id = 최신 리포트 id 인 것 중 최신 id,
# 없으면 그 장애의 최신 계획.
_LATEST_REPORT_ID = """(SELECT a.id FROM shared.analysis_reports a
         WHERE a.incident_id = i.id ORDER BY a.version DESC LIMIT 1)"""

_INCIDENT_SQL = f"""
SELECT i.id, i.zabbix_eventid, i.zabbix_triggerid, i.hostid, i.host_name, i.title,
       i.severity, i.status, i.started_at, i.resolved_at, i.tags_json,
       (SELECT r.status FROM shared.agent_runs r
         WHERE r.incident_id = i.id AND r.kind = 'analyze'
         ORDER BY r.started_at DESC, r.id DESC LIMIT 1) AS run_status,
       {_LATEST_REPORT_ID} AS report_id,
       (SELECT a.kind FROM shared.analysis_reports a
         WHERE a.incident_id = i.id ORDER BY a.version DESC LIMIT 1) AS report_kind,
       (SELECT p.id FROM shared.change_plans p
         WHERE p.incident_id = i.id
         ORDER BY CASE WHEN p.report_id = (SELECT a2.id FROM shared.analysis_reports a2
                     WHERE a2.incident_id = p.incident_id
                     ORDER BY a2.version DESC LIMIT 1) THEN 0 ELSE 1 END,
                  p.id DESC
         LIMIT 1) AS plan_id
FROM shared.incidents i
"""


def analysis_status(
    run_status: str | None,
    report_kind: str | None,
    severity: int,
    min_severity: int,
) -> str:
    """agent_runs.status + 최신 리포트 종류 → 화면 analysis.status 6값 (agent-api.md 3-2)."""
    if run_status is None:
        return "skipped" if severity < min_severity else "pending"
    if run_status in _RUNNING:
        return "running"
    if run_status == "failed":
        return "failed"
    # run 이 done: 리포트 종류로 구분. 리포트가 없으면 보여 줄 결과가 없으므로 failed
    if report_kind == "llm":
        return "done"
    if report_kind == "fallback":
        return "fallback"
    return "failed"


def _json(text: str | None, default: Any) -> Any:
    if text is None:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def _require_shared(db: Db) -> None:
    if not db.shared_ok:
        raise ApiError(
            503, "SHARED_DB_UNAVAILABLE", "공유 DB가 아직 준비되지 않았습니다"
        )


def _incident(row: sqlite3.Row, settings: Settings) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source": "zabbix",
        "zabbix": {
            "eventid": row["zabbix_eventid"],
            "triggerid": row["zabbix_triggerid"],
            "hostid": row["hostid"],
        },
        "host": {"id": row["hostid"], "name": row["host_name"]},
        "title": row["title"],
        "severity": {
            "level": row["severity"],
            "label": SEVERITY_LABELS[row["severity"]],
        },
        "status": row["status"],
        "started_at": row["started_at"],
        "resolved_at": row["resolved_at"],
        "tags": _json(row["tags_json"], []),
        "analysis": {
            "status": analysis_status(
                row["run_status"],
                row["report_kind"],
                row["severity"],
                settings.analyze_min_severity,
            ),
            "report_id": row["report_id"],
            "plan_id": row["plan_id"],
        },
    }


DETAIL_SQL = _INCIDENT_SQL + " WHERE i.id = ?"


def build_list_query(
    status: str | None,
    severity_min: int | None,
    after: tuple[str, int] | None,
    limit: int,
) -> tuple[str, list[Any]]:
    """API 10번 목록의 SQL 과 파라미터. 라우터와 성능 테스트(실행 계획)가 같은 조합을 쓰게 따로 뺐다."""
    where: list[str] = []
    params: list[Any] = []
    if status is not None:
        where.append("i.status = ?")
        params.append(status)
    if severity_min is not None:
        where.append("i.severity >= ?")
        params.append(severity_min)
    if after is not None:
        started_at, last_id = after
        where.append("(i.started_at < ? OR (i.started_at = ? AND i.id < ?))")
        params += [started_at, started_at, last_id]

    sql = _INCIDENT_SQL
    if where:
        sql += " WHERE " + " AND ".join(where)
    # 새 장애가 맨 위 (FR-FE-004)
    sql += " ORDER BY i.started_at DESC, i.id DESC LIMIT ?"
    return sql, [*params, limit]


@router.get("")
def list_incidents(
    status: Literal["problem", "resolved"] | None = None,
    severity_min: int | None = Query(None, ge=0, le=5),
    limit: int = Query(50, ge=1, le=100),
    cursor: str | None = None,
    _: dict = Depends(require_role("viewer")),
    db: Db = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_shared(db)

    after: tuple[str, int] | None = None
    if cursor:
        try:
            fields = decode_cursor(cursor)
            after = (str(fields["started_at"]), int(fields["id"]))
        except (ValueError, KeyError, TypeError):
            raise ApiError(
                422, "VALIDATION_ERROR", "cursor 형식이 올바르지 않습니다"
            ) from None

    # limit+1 개를 읽어 다음 쪽이 있는지 안다.
    sql, params = build_list_query(status, severity_min, after, limit + 1)
    rows = db.conn.execute(sql, params).fetchall()

    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = encode_cursor(started_at=last["started_at"], id=last["id"])
    return ok([_incident(r, settings) for r in page], next_cursor=next_cursor)


def _report(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "version": row["version"],
        "kind": row["kind"],
        "summary": row["summary"],
        "impact": _json(row["impact_json"], {}),
        "causes": _json(row["causes_json"], []),
        "facts": _json(row["facts_json"], []),
        "unknowns": _json(row["unknowns_json"], []),
        "next_checks": _json(row["next_checks_json"], []),
        "created_at": row["created_at"],
    }


def _evidence(row: sqlite3.Row) -> dict[str, Any]:
    # result_json 은 응답에 넣지 않는다
    return {
        "id": row["id"],
        "tool": row["tool"],
        "args": _json(row["args_json"], {}),
        "ok": bool(row["ok"]),
        "duration_ms": row["duration_ms"],
        "result_summary": row["result_summary"],
        "data_clock": row["data_clock"],
        "called_at": row["called_at"],
    }


def _plan(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "goal": row["goal"],
        "mode": row["mode"],
        "max_tier": row["max_tier"],
        "assumptions": _json(row["assumptions_json"], []),
    }


def _step(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "seq": row["seq"],
        "action_id": row["action_id"],
        "title": row["title"],
        "target": row["target"],
        "command_preview": row["command_preview"],
        "tier": row["tier"],
        "rationale": row["rationale"],
        "precheck": row["precheck"],
        "expected_effect": row["expected_effect"],
        "risk": row["risk"],
        "rollback": row["rollback"],
        "evidence_ids": _json(row["evidence_ids_json"], []),
    }


def _mail_log(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "recipient": row["recipient"],
        "status": row["status"],
        "attempts": row["attempts"],
        "error": row["error"],
        "created_at": row["created_at"],
        "sent_at": row["sent_at"],
    }


@router.get("/{incident_id}")
def incident_detail(
    incident_id: int,
    _: dict = Depends(require_role("viewer")),
    db: Db = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_shared(db)
    conn = db.conn

    row = conn.execute(DETAIL_SQL, (incident_id,)).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "장애를 찾을 수 없습니다")

    report = None
    evidence: list[dict[str, Any]] = []
    if row["report_id"] is not None:
        report_row = conn.execute(
            "SELECT * FROM shared.analysis_reports WHERE id = ?", (row["report_id"],)
        ).fetchone()
        report = _report(report_row)
        # 근거 = 리포트가 참조하는 run 의 tool_calls 전체
        evidence = [
            _evidence(r)
            for r in conn.execute(
                "SELECT * FROM shared.tool_calls WHERE run_id = ? ORDER BY seq",
                (report_row["run_id"],),
            )
        ]

    plan = None
    steps: list[dict[str, Any]] = []
    if row["plan_id"] is not None:
        plan_row = conn.execute(
            "SELECT * FROM shared.change_plans WHERE id = ?", (row["plan_id"],)
        ).fetchone()
        plan = _plan(plan_row)
        steps = [
            _step(r)
            for r in conn.execute(
                "SELECT * FROM shared.plan_steps WHERE plan_id = ? ORDER BY seq",
                (row["plan_id"],),
            )
        ]

    mail_logs = [
        _mail_log(r)
        for r in conn.execute(
            "SELECT * FROM mail_logs WHERE incident_id = ? ORDER BY id", (incident_id,)
        )
    ]

    return ok(
        {
            "incident": _incident(row, settings),
            "report": report,
            "evidence": evidence,
            "plan": plan,
            "steps": steps,
            "mail_logs": mail_logs,
        }
    )
