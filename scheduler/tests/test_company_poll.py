"""회사별 폴링·019 이관 (결정 019, contracts/db-schema.sql 규칙 8)."""

import copy
import json
import threading
from datetime import UTC, datetime

import pytest
import zabbix_ro
from shared_db import open_db

from dejafix_scheduler.__main__ import run
from dejafix_scheduler.config import DEFAULT_MOCK_FILE, Settings
from dejafix_scheduler.migrate import MigrationError, has_company, migrate
from dejafix_scheduler.poller import JOB, Scope, poll_once
from dejafix_scheduler.source import CompanySources, MockSource

NOW = datetime(2026, 11, 26, 3, 0, 0, tzinfo=UTC)


def _problem(eventid, name="CPU high", resolved=False):
    return {
        "eventid": str(eventid),
        "objectid": f"t{eventid}",
        "name": name,
        "severity": "4",
        "clock": "1790000000",
        "r_eventid": "9" if resolved else "0",
        "r_clock": "1790000100" if resolved else "0",
        "acknowledged": "0",
        "tags": [],
    }


def _src(*problems):
    return MockSource({"problems": list(problems), "triggers": {}})


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "shared.db", "shared")
    yield c
    c.close()


def _rows(conn, company):
    return conn.execute(
        "SELECT zabbix_eventid, zabbix_conn_id, status, resolved_reason, title FROM incidents "
        "WHERE company_id=? ORDER BY zabbix_conn_id, zabbix_eventid",
        (company,),
    ).fetchall()


def _run_analysis(conn, incident_id):
    conn.execute(
        "INSERT INTO agent_runs(id, kind, incident_id, caller, status, started_at) "
        "VALUES ('r_1', 'analyze', ?, 'worker', 'done', '2026-11-26T00:00:00Z')",
        (incident_id,),
    )
    conn.commit()


def test_migration_keeps_rows_ids_and_references(conn):
    poll_once(conn, _src(_problem(100), _problem(101, resolved=True)), NOW)
    first_id = conn.execute(
        "SELECT id FROM incidents WHERE zabbix_eventid='100'"
    ).fetchone()[0]
    _run_analysis(
        conn, first_id
    )  # agent_runs 가 incidents 를 가리킨다 → FK 켠 채로는 DROP 실패
    assert migrate(conn, "catbooks", "zc_aaaaaaaaaaaa") == [
        "incidents",
        "scheduler_jobs",
    ]
    assert has_company(conn, "incidents") and has_company(conn, "scheduler_jobs")
    assert _rows(conn, "catbooks") == [
        ("100", "zc_aaaaaaaaaaaa", "problem", None, "CPU high"),
        ("101", "zc_aaaaaaaaaaaa", "resolved", "zabbix", "CPU high"),
    ]
    assert (
        conn.execute("SELECT id FROM incidents WHERE zabbix_eventid='100'").fetchone()[
            0
        ]
        == first_id
    )
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute(
        "SELECT company_id FROM scheduler_jobs WHERE job=?", (JOB,)
    ).fetchone() == ("catbooks",)
    assert migrate(conn, "catbooks", "zc_aaaaaaaaaaaa") == []  # 두 번째는 건너뛴다


def test_migration_off_without_default_company(conn):
    assert migrate(conn, None, "env") == []
    assert not has_company(conn, "incidents")


def test_insert_without_company_is_refused_after_migration(conn):
    migrate(conn, "catbooks", "env")
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO incidents(zabbix_eventid, zabbix_triggerid, title, severity, status, "
            "started_at, first_seen_at, last_seen_at) VALUES ('1','t','x',1,'problem','a','a','a')"
        )


def test_broken_reference_rolls_back(conn):
    poll_once(conn, _src(_problem(100)), NOW)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        "INSERT INTO agent_runs(id, kind, incident_id, caller, status, started_at) "
        "VALUES ('r_x', 'analyze', 999, 'worker', 'done', '2026-11-26T00:00:00Z')"
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(MigrationError):
        migrate(conn, "catbooks", "env")
    assert not has_company(conn, "incidents")  # 그대로 남는다
    assert conn.execute("SELECT count(*) FROM incidents").fetchone()[0] == 1


def test_companies_do_not_mix(conn):
    migrate(conn, "catbooks", "env")
    poll_once(conn, _src(_problem(100, "cb")), NOW, Scope("catbooks", "env"))
    poll_once(
        conn, _src(_problem(100, "nubi")), NOW, Scope("c-cf2f0d", "zc_111111111111")
    )
    assert [r[4] for r in _rows(conn, "catbooks")] == ["cb"]
    assert [r[4] for r in _rows(conn, "c-cf2f0d")] == [
        "nubi"
    ]  # 같은 eventid 라도 회사마다 따로
    jobs = conn.execute(
        "SELECT company_id FROM scheduler_jobs WHERE job=? ORDER BY 1", (JOB,)
    ).fetchall()
    assert jobs == [("c-cf2f0d",), ("catbooks",)]


def test_connection_change_closes_old_problems_and_keeps_new_same_eventid(conn):
    """준하 님 #214 리뷰 재현: 옛 100·101 → 새 101·102."""
    migrate(conn, "catbooks", "env")
    old, new = (
        Scope("c-cf2f0d", "zc_000000000001"),
        Scope("c-cf2f0d", "zc_000000000002"),
    )
    poll_once(conn, _src(_problem(100, "old100"), _problem(101, "old101")), NOW, old)
    r = poll_once(
        conn, _src(_problem(101, "new101"), _problem(102, "new102")), NOW, new
    )
    assert r.closed == 2 and r.inserted == 2
    assert _rows(conn, "c-cf2f0d") == [
        ("100", "zc_000000000001", "resolved", "connection_changed", "old100"),
        ("101", "zc_000000000001", "resolved", "connection_changed", "old101"),
        ("101", "zc_000000000002", "problem", None, "new101"),
        ("102", "zc_000000000002", "problem", None, "new102"),
    ]


def test_company_sources_never_fall_back(tmp_path):
    path = tmp_path / "zabbix_connection.json"
    env = {
        "ZABBIX_CONNECTION_FILE": str(path),
        "ZABBIX_URL": "http://env-zbx",
        "ZABBIX_API_TOKEN": "env-t",
    }
    srcs = CompanySources("catbooks", False, DEFAULT_MOCK_FILE, env)
    env_id = zabbix_ro.env_conn_id("http://env-zbx")
    # 누비투어는 연결 전이라 폴링하지 않는다
    assert srcs.scopes() == [("catbooks", env_id)]
    zabbix_ro.save_connection(path, "http://nubi", "nb", "", "", "c-cf2f0d", "catbooks")
    scopes = dict(srcs.scopes())
    assert scopes["catbooks"] == env_id and scopes["c-cf2f0d"].startswith("zc_")
    assert srcs.source("c-cf2f0d").client.client.url == "http://nubi"


def test_run_in_company_mode_with_mock(tmp_path, monkeypatch):
    monkeypatch.delenv("ZABBIX_URL", raising=False)
    monkeypatch.setenv("ZABBIX_CONNECTION_FILE", str(tmp_path / "none.json"))
    settings = Settings(tmp_path / "shared.db", 5, True, DEFAULT_MOCK_FILE, "catbooks")
    assert run(settings, threading.Event(), max_cycles=1, kb=None) == 1
    c = open_db(tmp_path / "shared.db", "shared")
    data = json.loads(DEFAULT_MOCK_FILE.read_text(encoding="utf-8"))
    assert (
        c.execute("SELECT count(DISTINCT company_id) FROM incidents").fetchone()[0] == 1
    )
    assert c.execute(
        "SELECT count(*) FROM incidents WHERE company_id='catbooks'"
    ).fetchone()[0] == len(copy.deepcopy(data)["problems"])
    c.close()


def test_broken_connection_file_skips_cycle_and_closes_nothing(tmp_path, conn):
    """연결 파일을 못 읽으면 연결 변경으로 보지 않는다(준하 님 #216 리뷰)."""
    path = tmp_path / "zabbix_connection.json"
    zabbix_ro.save_connection(path, "http://cb", "t", "", "", "catbooks", "catbooks")
    env = {"ZABBIX_CONNECTION_FILE": str(path), "ZABBIX_URL": "http://env-zbx"}
    srcs = CompanySources("catbooks", False, DEFAULT_MOCK_FILE, env)
    ((company, conn_id),) = srcs.scopes()
    migrate(conn, "catbooks", conn_id)
    poll_once(conn, _src(_problem(100)), NOW, Scope(company, conn_id))
    path.write_text("{half-written", encoding="utf-8")
    assert srcs.scopes() == []  # .env 로 떨어져 conn_id 가 바뀌지 않는다
    assert _rows(conn, "catbooks")[0][2] == "problem"
