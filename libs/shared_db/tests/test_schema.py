import sqlite3

import pytest

from shared_db import (
    SchemaError,
    apply_schema,
    connect,
    find_contract,
    load_dev_seed,
    open_db,
)

SHARED_TABLES = {
    "incidents",
    "scheduler_jobs",
    "agent_runs",
    "tool_calls",
    "analysis_reports",
    "change_plans",
    "plan_steps",
    "conversations",
    "messages",
}
BACKEND_TABLES = {"users", "mail_logs", "resolution_notes"}
T = "2026-10-16T01:20:00Z"


def tables(conn):
    return {
        r[0]
        for r in conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        )
    }


def test_contract_found():
    assert find_contract().name == "db-schema.sql"


def test_shared_idempotent_twice(tmp_path):
    db = tmp_path / "shared.db"
    open_db(db, "shared").close()
    conn = open_db(db, "shared")  # 두 번째 적용도 오류 없음 (FR-DATA-003)
    assert tables(conn) == SHARED_TABLES
    conn.close()


def test_backend_section_only(tmp_path):
    conn = open_db(tmp_path / "backend.db", "backend")
    assert tables(conn) == BACKEND_TABLES  # shared 테이블이 섞이지 않음
    conn.close()


def test_pragmas(tmp_path):
    conn = connect(tmp_path / "x.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    conn.close()


def test_unknown_section(tmp_path):
    with pytest.raises(SchemaError):
        apply_schema(connect(tmp_path / "x.db"), "everything")


def test_plan_mode_preview_only(tmp_path):
    # SAFE-04: change_plans.mode 는 'preview' 외 값을 넣을 수 없다
    conn = open_db(tmp_path / "shared.db", "shared")
    conn.execute(
        "insert into agent_runs(id,kind,caller,status,started_at) values('r_1','analyze','worker','done',?)",
        (T,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "insert into change_plans(run_id,title,mode,max_tier,created_at) values('r_1','p','execute','A',?)",
            (T,),
        )
    conn.close()


def test_dev_seed_loads_and_reruns(tmp_path):
    conn = open_db(tmp_path / "shared.db", "shared")
    load_dev_seed(conn, "shared")
    load_dev_seed(conn, "shared")  # INSERT OR IGNORE 라 재실행 안전
    assert conn.execute("select count(*) from incidents").fetchone()[0] == 6
    assert conn.execute("select count(*) from analysis_reports").fetchone()[0] == 2
    conn.close()


def test_backend_attach_readonly(tmp_path):
    # Backend 방식: backend.db 를 URI 모드로 열고 shared.db 를 읽기 전용으로 붙인다
    shared = tmp_path / "shared.db"
    open_db(shared, "shared").close()
    backend = tmp_path / "backend.db"
    conn = connect(backend.as_uri(), uri=True)
    apply_schema(conn, "backend")
    conn.execute(f"ATTACH '{shared.as_uri()}?mode=ro' AS shared")
    assert conn.execute("select count(*) from shared.incidents").fetchone()[0] == 0
    with pytest.raises(sqlite3.OperationalError):
        conn.execute(
            "insert into shared.incidents(zabbix_eventid,zabbix_triggerid,title,severity,status,"
            "started_at,first_seen_at,last_seen_at) values('1','2','t',4,'problem',?,?,?)",
            (T, T, T),
        )
    conn.close()
