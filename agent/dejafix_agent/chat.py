"""채팅 (T54, FR-AG-009·011, contracts/agent-api.md 1-2).

- 장애 맥락(장애·최신 리포트)을 데이터로 감싸 붙인다. 사용자 문장 속 지시를 규칙보다 앞세우지 않는다.
- LLM 이 없거나 실패하면 규칙 기반 답변: 최신 리포트 요약 + 수집된 사실만.
  질문 대상이 수집되지 않았으면 "확인할 수 없음 · NOT_COLLECTED".
- 저장: conversations, messages(user·assistant), agent_runs(kind='chat').
SQLite 연결은 단계마다 새로 열고 닫는다(스트림 중 스레드가 바뀔 수 있음).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared_db import open_db

from .collect import iso, utcnow
from .config import Settings
from .llm import LlmError, complete_text
from .packs import Pack


class ChatError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class ChatStart:
    conversation_id: str
    run_id: str
    message_id: int
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Answer:
    content: str
    evidence_ids: list[str]
    unknowns: list[dict[str, str]]
    from_llm: bool
    error: str | None = None


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = open_db(db_path, "shared")
    conn.row_factory = sqlite3.Row
    return conn


def _load_context(conn: sqlite3.Connection, incident_id: int | None) -> dict[str, Any]:
    if not incident_id:
        return {}
    inc = conn.execute(
        "SELECT * FROM incidents WHERE id = ?", (incident_id,)
    ).fetchone()
    if inc is None:
        return {}
    rep = conn.execute(
        "SELECT * FROM analysis_reports WHERE incident_id = ? ORDER BY version DESC LIMIT 1",
        (incident_id,),
    ).fetchone()
    ctx: dict[str, Any] = {
        "incident": {
            k: inc[k]
            for k in ("id", "host_name", "title", "severity", "status", "started_at")
        }
    }
    if rep is not None:
        ctx["report"] = {
            "kind": rep["kind"],
            "summary": rep["summary"],
            "facts": json.loads(rep["facts_json"]),
            "unknowns": json.loads(rep["unknowns_json"]),
            "causes": json.loads(rep["causes_json"]),
        }
    return ctx


def start(
    db_path: Path,
    body: dict[str, Any],
    user_id: int | None,
    caller: str,
    model: str | None,
) -> ChatStart:
    message = (body.get("message") or "").strip()
    if not message:
        raise ChatError(400, "BAD_REQUEST", "message 가 비어 있습니다")
    context_in = body.get("context") or {}
    incident_id = context_in.get("incident_id")
    now = iso(utcnow())
    conn = _conn(db_path)
    try:
        conv_id = body.get("conversation_id")
        if conv_id:
            row = conn.execute(
                "SELECT user_id, incident_id FROM conversations WHERE id = ?",
                (conv_id,),
            ).fetchone()
            if row is None or (
                user_id is not None and row["user_id"] not in (None, user_id)
            ):
                raise ChatError(
                    404, "CONVERSATION_NOT_FOUND", "대화를 찾을 수 없습니다"
                )
            incident_id = incident_id or row["incident_id"]
        else:
            conv_id = "c_" + uuid.uuid4().hex[:12]
            conn.execute(
                """INSERT INTO conversations(id, user_id, caller, incident_id, title, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (conv_id, user_id, caller, incident_id, message[:40], now, now),
            )
        run_id = "r_" + uuid.uuid4().hex[:12]
        conn.execute(
            """INSERT INTO agent_runs(id, kind, incident_id, conversation_id, caller, requested_by, status, model, started_at)
               VALUES (?, 'chat', ?, ?, ?, ?, 'analyzing', ?, ?)""",
            (run_id, incident_id, conv_id, caller, user_id, model, now),
        )
        cur = conn.execute(
            "INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (conv_id, message, now),
        )
        conn.commit()
        return ChatStart(
            conv_id, run_id, cur.lastrowid, _load_context(conn, incident_id)
        )
    finally:
        conn.close()


def rule_based(message: str, context: dict[str, Any], pack: Pack) -> Answer:
    text = message.lower()
    report = context.get("report")
    incident = context.get("incident")
    if not incident:
        return Answer(
            "장애 맥락 없이 받은 질문입니다. 조회한 데이터가 없어 확인할 수 없습니다.",
            [],
            [{"label": message[:40], "reason": "NOT_COLLECTED"}],
            False,
        )
    head = f"{incident['host_name'] or '호스트'}의 장애 '{incident['title']}'에 대한 답입니다."
    if not report:
        return Answer(
            head + " 아직 분석 리포트가 없어 확인할 수 없습니다.",
            [],
            [{"label": "분석 리포트", "reason": "NO_DATA"}],
            False,
        )
    hits = [f for f in report["facts"] if f["label"].split(" · ")[0].lower() in text]
    if hits:
        lines, evidence, unknowns = [], [], []
        for f in hits:
            if f["value"] is None:
                lines.append(f"- {f['label']}: 확인할 수 없음 · {f['unknown_reason']}")
                unknowns.append(
                    {"label": f["label"], "reason": f["unknown_reason"] or "NO_DATA"}
                )
            else:
                unit = f.get("unit") or ""
                lines.append(
                    f"- {f['label']}: {f['value']}{unit} (근거 {', '.join(f['evidence_ids'])})"
                )
                evidence += f["evidence_ids"]
        return Answer(head + "\n" + "\n".join(lines), evidence, unknowns, False)
    return Answer(
        head
        + f" 리포트 요약: {report['summary']}\n질문하신 내용은 수집되지 않아 확인할 수 없습니다.",
        [],
        [{"label": message[:40], "reason": "NOT_COLLECTED"}],
        False,
    )


def answer(
    settings: Settings, pack: Pack, message: str, context: dict[str, Any]
) -> Answer:
    fallback = rule_based(message, context, pack)
    if settings.llm_mode != "real":
        return fallback
    prompt = pack.prompts.get("chat", "{context}").replace(
        "{context}", json.dumps(context, ensure_ascii=False)
    )
    try:
        content = complete_text(settings, prompt + "\n\n질문: " + message)
    except LlmError as exc:
        fallback.error = exc.code
        return fallback
    return Answer(content, [], [], True)


def finish(
    db_path: Path, start_: ChatStart, ans: Answer, error: str | None = None
) -> int:
    now = iso(utcnow())
    conn = _conn(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO messages(conversation_id, role, content, run_id, created_at) VALUES (?, 'assistant', ?, ?, ?)",
            (start_.conversation_id, ans.content, start_.run_id, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, start_.conversation_id),
        )
        conn.execute(
            "UPDATE agent_runs SET status = 'done', error = ?, finished_at = ? WHERE id = ?",
            (error or ans.error, now, start_.run_id),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
