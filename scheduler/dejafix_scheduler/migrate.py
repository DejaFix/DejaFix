"""결정 019 이관 — Scheduler 몫 표(incidents, scheduler_jobs)에 회사 칸을 넣는다.

contracts/db-schema.sql 규칙 8 의 절차를 그대로 따른다. 데이터는 지우지 않는다.
- `DEFAULT_COMPANY_ID` 가 없으면 하지 않는다(회사 나누기 꺼짐, 지금 스키마 그대로).
- 칸이 이미 있으면 건너뛴다(기동할 때마다 불러도 된다).
- ALTER ... ADD COLUMN 을 쓰지 않고 표를 다시 만든다(NOT NULL 칸에 DEFAULT 가 남지 않게).
- foreign_keys 는 트랜잭션 밖에서 끈다(켠 채로 incidents 를 지우면 agent_runs 등이 가리켜 DROP 이 실패한다).
- foreign_key_check 에 한 줄이라도 나오면 ROLLBACK 하고 기동을 멈춘다(MigrationError, 로그에 표 이름만).
"""

from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger("scheduler")


class MigrationError(RuntimeError):
    """019 이관 실패. 기동을 멈춘다."""


_INCIDENTS = """CREATE TABLE incidents__new (
  id               INTEGER PRIMARY KEY,
  company_id       TEXT    NOT NULL,
  zabbix_conn_id   TEXT    NOT NULL,
  zabbix_eventid   TEXT    NOT NULL,
  zabbix_triggerid TEXT    NOT NULL,
  hostid           TEXT,
  host_name        TEXT,
  title            TEXT    NOT NULL,
  severity         INTEGER NOT NULL CHECK (severity BETWEEN 0 AND 5),
  status           TEXT    NOT NULL CHECK (status IN ('problem','resolved')),
  started_at       TEXT    NOT NULL,
  resolved_at      TEXT,
  resolved_reason  TEXT    CHECK (resolved_reason IS NULL OR resolved_reason IN ('zabbix','connection_changed')),
  acknowledged     INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0,1)),
  tags_json        TEXT    NOT NULL DEFAULT '[]',
  first_seen_at    TEXT    NOT NULL,
  last_seen_at     TEXT    NOT NULL,
  UNIQUE (company_id, zabbix_conn_id, zabbix_eventid)
)"""

_INCIDENT_COLS = (
    "id, zabbix_eventid, zabbix_triggerid, hostid, host_name, title, severity, status, "
    "started_at, resolved_at, acknowledged, tags_json, first_seen_at, last_seen_at"
)

_INCIDENT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_incidents_company_status ON incidents(company_id, status, severity)",
    "CREATE INDEX IF NOT EXISTS ix_incidents_company_started ON incidents(company_id, started_at)",
    # 계약 원래 색인 이름(apply_schema 가 기동마다 IF NOT EXISTS 로 다시 부른다)
    "CREATE INDEX IF NOT EXISTS ix_incidents_status ON incidents(status, severity)",
    "CREATE INDEX IF NOT EXISTS ix_incidents_started ON incidents(started_at)",
)

_JOBS = """CREATE TABLE scheduler_jobs__new (
  company_id   TEXT NOT NULL,
  job          TEXT NOT NULL,
  last_run_at  TEXT,
  last_ok_at   TEXT,
  status       TEXT CHECK (status IS NULL OR status IN ('ok','error')),
  message      TEXT,
  PRIMARY KEY (company_id, job)
)"""


def has_company(conn: sqlite3.Connection, table: str) -> bool:
    return any(
        row[1] == "company_id" for row in conn.execute(f"PRAGMA table_info({table})")
    )


def _rebuild(
    conn: sqlite3.Connection,
    table: str,
    create: str,
    copy: str,
    args: tuple,
    indexes: tuple,
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
            conn.execute(copy, args)  # 4) id 그대로
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


def migrate(
    conn: sqlite3.Connection, default_company: str | None, conn_id: str
) -> list[str]:
    """Scheduler 몫 표를 이관한다. 바꾼 표 이름 목록. default_company 가 없으면 아무것도 하지 않는다.

    conn_id: 이관 시각 기본 회사의 지금 연결 구분값(연결 파일 conn_id, 없으면 'env', 연결이 없으면 'legacy').
    """
    if not default_company:
        return []
    done = []
    if _rebuild(
        conn,
        "incidents",
        _INCIDENTS,
        f"""INSERT INTO incidents__new (company_id, zabbix_conn_id, resolved_reason, {_INCIDENT_COLS})
            SELECT ?, ?, CASE status WHEN 'resolved' THEN 'zabbix' END, {_INCIDENT_COLS}
            FROM incidents""",
        (default_company, conn_id),
        _INCIDENT_INDEXES,
    ):
        done.append("incidents")
    if _rebuild(
        conn,
        "scheduler_jobs",
        _JOBS,
        """INSERT INTO scheduler_jobs__new (company_id, job, last_run_at, last_ok_at, status, message)
           SELECT ?, job, last_run_at, last_ok_at, status, message FROM scheduler_jobs""",
        (default_company,),
        (),
    ):
        done.append("scheduler_jobs")
    return done
