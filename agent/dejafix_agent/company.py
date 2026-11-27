"""회사 (결정 019) — Agent 몫.

- `DEFAULT_COMPANY_ID` 가 없으면 회사 나누기가 꺼져 있다: 이관하지 않고 지금 스키마·동작 그대로.
- 켜져 있으면 기동할 때 Agent 몫 표(agent_runs, conversations)를 contracts/db-schema.sql 규칙 8 절차로
  한 번 이관한다(칸이 이미 있으면 건너뜀, 데이터는 지우지 않음, 기존 행은 기본 회사).
- 이관 뒤 이 두 표에 쓰는 코드는 company_id 를 늘 직접 넣는다(기본값 없음).
- Agent·MCP 는 아직 회사별 MCP 세션이 없어 기본 회사 Zabbix 만 본다. 그래서 자동 분석은
  기본 회사 장애만 하고(다른 회사 장애를 기본 회사 Zabbix 로 분석해 섞지 않게), 대화는 Backend 가
  기본 회사가 아닌 요청을 503 으로 막는다(backend routers/chat.py).
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger("dejafix.agent.company")


class MigrationError(RuntimeError):
    """019 이관 실패. 기동을 멈춘다."""


_AGENT_RUNS = """CREATE TABLE agent_runs__new (
  id              TEXT    PRIMARY KEY,
  company_id      TEXT    NOT NULL,
  kind            TEXT    NOT NULL CHECK (kind IN ('analyze','plan','chat')),
  incident_id     INTEGER REFERENCES incidents(id),
  conversation_id TEXT,
  caller          TEXT    NOT NULL,
  requested_by    INTEGER,
  status          TEXT    NOT NULL CHECK (status IN
                    ('queued','collecting','analyzing','validating','reported','planning','done','failed')),
  model           TEXT,
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  tokens_in       INTEGER,
  tokens_out      INTEGER,
  cost_usd        REAL,
  error           TEXT,
  started_at      TEXT    NOT NULL,
  finished_at     TEXT
)"""

_AGENT_RUNS_COLS = (
    "id, kind, incident_id, conversation_id, caller, requested_by, status, model, "
    "tool_call_count, tokens_in, tokens_out, cost_usd, error, started_at, finished_at"
)

_AGENT_RUNS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_agent_runs_company ON agent_runs(company_id, kind, started_at)",
    # 계약 원래 색인 이름(apply_schema 가 기동마다 IF NOT EXISTS 로 다시 부른다)
    "CREATE INDEX IF NOT EXISTS ix_agent_runs_incident ON agent_runs(incident_id, kind, started_at)",
)

_CONVERSATIONS = """CREATE TABLE conversations__new (
  id          TEXT    PRIMARY KEY,
  company_id  TEXT    NOT NULL,
  user_id     INTEGER,
  caller      TEXT    NOT NULL DEFAULT 'backend',
  incident_id INTEGER REFERENCES incidents(id),
  title       TEXT,
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL
)"""

_CONVERSATIONS_COLS = "id, user_id, caller, incident_id, title, created_at, updated_at"

_CONVERSATIONS_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_conversations_company ON conversations(company_id, updated_at)",
)


def has_company(conn: sqlite3.Connection, table: str) -> bool:
    return any(
        row[1] == "company_id" for row in conn.execute(f"PRAGMA table_info({table})")
    )


def _rebuild(
    conn: sqlite3.Connection,
    table: str,
    create: str,
    cols: str,
    company: str,
    indexes: tuple[str, ...],
) -> bool:
    if has_company(conn, table):
        return False
    conn.commit()
    conn.execute("PRAGMA foreign_keys=OFF")  # 1) 트랜잭션 밖
    try:
        conn.execute("BEGIN IMMEDIATE")  # 2)
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table}__new")
            conn.execute(create)  # 3)
            conn.execute(  # 4) id 그대로
                f"INSERT INTO {table}__new (company_id, {cols}) SELECT ?, {cols} FROM {table}",
                (company,),
            )
            conn.execute(f"DROP TABLE {table}")  # 5)
            conn.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
            for sql in indexes:  # 6)
                conn.execute(sql)
            if conn.execute("PRAGMA foreign_key_check").fetchall():  # 7)
                raise MigrationError(f"019 이관 foreign_key_check 실패: {table}")
            conn.execute("COMMIT")  # 8)
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
    log.info("019 이관 끝: %s", table)
    return True


def migrate(conn: sqlite3.Connection, default_company: str | None) -> list[str]:
    """Agent 몫 표를 이관한다. 바꾼 표 이름 목록. default_company 가 없으면 아무것도 하지 않는다."""
    company = (default_company or "").strip()
    if not company:
        return []
    done = []
    if _rebuild(
        conn,
        "agent_runs",
        _AGENT_RUNS,
        _AGENT_RUNS_COLS,
        company,
        _AGENT_RUNS_INDEXES,
    ):
        done.append("agent_runs")
    if _rebuild(
        conn,
        "conversations",
        _CONVERSATIONS,
        _CONVERSATIONS_COLS,
        company,
        _CONVERSATIONS_INDEXES,
    ):
        done.append("conversations")
    return done


def write_cols(
    conn: sqlite3.Connection, table: str, company: str | None
) -> tuple[str, str, tuple]:
    """INSERT 에 붙일 (칸, 자리표시, 값). 이관 전(칸 없음)이면 빈 값.

    이관 뒤인데 회사가 비면 MigrationError — 회사 없이 쓰지 않는다(계약 규칙 8).
    """
    if not has_company(conn, table):
        return "", "", ()
    value = (company or "").strip()
    if not value:
        raise MigrationError(f"{table} 에 회사 없이 쓰려 함")
    return ", company_id", ", ?", (value,)
