"""결정 019 — Agent 몫 이관(agent_runs, conversations)과 회사별 쓰기 (contracts/db-schema.sql 규칙 8)."""

import sqlite3

import pytest

from dejafix_agent import chat, company, worker
from dejafix_agent.config import Settings
from shared_db import open_db

CB = "catbooks"
NUBI = "c-cf2f0d"
T = "2026-11-27T00:00:00Z"


def _seed(conn: sqlite3.Connection) -> None:
    """옛 모양(회사 칸 없음) 데이터: 장애 1 · 분석 run 1 · 근거 1 · 대화 1 · 메시지 1."""
    conn.execute(
        "INSERT INTO incidents (id, zabbix_eventid, zabbix_triggerid, title, severity, status,"
        " started_at, first_seen_at, last_seen_at) VALUES (1, '100', 't1', 'old', 4, 'problem', ?, ?, ?)",
        (T, T, T),
    )
    conn.execute(
        "INSERT INTO agent_runs (id, kind, incident_id, caller, status, started_at)"
        " VALUES ('r_old', 'analyze', 1, 'worker', 'done', ?)",
        (T,),
    )
    conn.execute(
        "INSERT INTO tool_calls (id, run_id, seq, tool, args_json, ok, duration_ms, called_at)"
        " VALUES ('ev_1', 'r_old', 1, 'zabbix_get_problem', '{}', 1, 5, ?)",
        (T,),
    )
    conn.execute(
        "INSERT INTO conversations (id, user_id, caller, incident_id, title, created_at, updated_at)"
        " VALUES ('c_old', 1, 'backend', 1, 'hi', ?, ?)",
        (T, T),
    )
    conn.execute(
        "INSERT INTO messages (conversation_id, role, content, run_id, created_at)"
        " VALUES ('c_old', 'user', 'hi', 'r_old', ?)",
        (T,),
    )
    conn.commit()


@pytest.fixture
def db(tmp_path):
    conn = open_db(tmp_path / "shared.db", "shared")
    conn.execute("PRAGMA foreign_keys=ON")
    _seed(conn)
    yield conn
    conn.close()


def test_migration_with_foreign_keys_on_keeps_rows_and_references(db):
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert company.migrate(db, CB) == ["agent_runs", "conversations"]
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("SELECT id, company_id FROM agent_runs").fetchall() == [
        ("r_old", CB)
    ]
    assert db.execute("SELECT id, company_id FROM conversations").fetchall() == [
        ("c_old", CB)
    ]
    # 다른 표의 참조가 그대로 맞는다
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert db.execute("SELECT run_id FROM tool_calls").fetchone()[0] == "r_old"
    assert db.execute("SELECT conversation_id, run_id FROM messages").fetchone() == (
        "c_old",
        "r_old",
    )
    # 두 번 불러도 건너뜀(기동마다 불러도 됨) + 계약 색인 다시 적용해도 됨
    assert company.migrate(db, CB) == []
    from shared_db import apply_schema

    apply_schema(db, "shared")


def test_insert_without_company_fails_after_migration(db):
    company.migrate(db, CB)
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO agent_runs (id, kind, caller, status, started_at)"
            " VALUES ('r_x', 'chat', 'backend', 'queued', ?)",
            (T,),
        )
    with pytest.raises(company.MigrationError):
        company.write_cols(db, "agent_runs", "")


def test_no_default_company_means_no_migration(db):
    assert company.migrate(db, "") == []
    assert not company.has_company(db, "agent_runs")
    assert company.write_cols(db, "agent_runs", None) == ("", "", ())


def test_failed_check_rolls_back(db, monkeypatch):
    db.execute("PRAGMA foreign_keys=OFF")
    # 없는 장애를 가리키는 run → foreign_key_check 가 걸려 롤백하고 기동을 멈춘다
    db.execute(
        "INSERT INTO agent_runs (id, kind, incident_id, caller, status, started_at)"
        " VALUES ('r_bad', 'analyze', 999, 'worker', 'done', ?)",
        (T,),
    )
    db.commit()
    with pytest.raises(company.MigrationError):
        company.migrate(db, CB)
    assert not company.has_company(db, "agent_runs")
    assert db.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 2


def _scope_incidents(conn: sqlite3.Connection) -> None:
    """Scheduler 019 이관 흉내: incidents 에 회사 칸 + 누비투어 장애 하나."""
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("ALTER TABLE incidents ADD COLUMN company_id TEXT")
    conn.execute("UPDATE incidents SET company_id = ?", (CB,))
    conn.execute(
        "INSERT INTO incidents (id, zabbix_eventid, zabbix_triggerid, title, severity, status,"
        " started_at, first_seen_at, last_seen_at, company_id)"
        " VALUES (2, '200', 't2', 'nubi', 5, 'problem', ?, ?, ?, ?)",
        (T, T, T, NUBI),
    )
    conn.execute(
        "INSERT INTO incidents (id, zabbix_eventid, zabbix_triggerid, title, severity, status,"
        " started_at, first_seen_at, last_seen_at, company_id)"
        " VALUES (3, '300', 't3', 'cb new', 5, 'problem', ?, ?, ?, ?)",
        (T, T, T, CB),
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")


def test_worker_only_analyzes_default_company_after_scheduler_migration(db):
    _scope_incidents(db)
    picked = worker.pending_incidents(db, 0, default_company=CB)
    assert [i["id"] for i in picked] == [3]  # 1 은 이미 분석됨, 2 는 누비투어라 안 함
    # 회사 나누기 꺼짐이면 지금처럼
    assert [i["id"] for i in worker.pending_incidents(db, 0)] == [2, 3]


def test_chat_writes_company_after_migration(tmp_path):
    path = tmp_path / "shared.db"
    conn = open_db(path, "shared")
    company.migrate(conn, CB)
    conn.close()
    started = chat.start(path, {"message": "상태 알려 줘"}, 1, "backend", "fake", CB)
    conn = sqlite3.connect(path)
    assert (
        conn.execute(
            "SELECT company_id FROM conversations WHERE id = ?",
            (started.conversation_id,),
        ).fetchone()[0]
        == CB
    )
    assert (
        conn.execute(
            "SELECT company_id FROM agent_runs WHERE id = ?", (started.run_id,)
        ).fetchone()[0]
        == CB
    )
    conn.close()


def test_settings_read_default_company():
    s = Settings.from_env({"DEFAULT_COMPANY_ID": " catbooks "})
    assert s.default_company_id == CB
    assert Settings.from_env({}).default_company_id == ""
