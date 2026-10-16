import sqlite3

import pytest

from dejafix_backend.config import ROOT, Settings, get_settings
from dejafix_backend.db import db_file, init_backend_db, open_db, split_zones


def test_attach_write_is_rejected(env, helpers):
    """FR-BE-014: Backend 연결로 shared.incidents 에 쓰면 readonly 오류."""
    helpers.build_shared_db(env.shared)
    init_backend_db(get_settings())
    db = open_db(get_settings())
    try:
        assert db.shared_ok is True
        count = db.conn.execute("SELECT COUNT(*) FROM shared.incidents").fetchone()[0]
        assert count == 6
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.conn.execute(
                "INSERT INTO shared.incidents (zabbix_eventid, zabbix_triggerid, title,"
                " severity, status, started_at, first_seen_at, last_seen_at)"
                " VALUES ('x', 'x', 'x', 1, 'problem', 'x', 'x', 'x')"
            )
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.conn.execute("DELETE FROM shared.incidents")
    finally:
        db.close()


def test_shared_missing_is_waiting_not_error(env, helpers):
    """shared.db 가 아직 없으면 attach 를 건너뛰고 shared_ok=False (요청마다 재시도)."""
    init_backend_db(get_settings())
    db = open_db(get_settings())
    try:
        assert db.shared_ok is False
    finally:
        db.close()

    helpers.build_shared_db(
        env.shared
    )  # 나중에 Agent·Scheduler 가 만들면 다음 요청부터 보인다
    db = open_db(get_settings())
    try:
        assert db.shared_ok is True
    finally:
        db.close()


def test_backend_zone_only_no_shadow_tables(env):
    """구역을 섞어 적용하면 backend.db 에 그림자 incidents 가 생긴다 — backend 구역만 적용했는지."""
    init_backend_db(get_settings())
    conn = sqlite3.connect(env.backend)
    names = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()
    assert {"users", "mail_logs"} <= names
    assert names.isdisjoint(
        {"incidents", "agent_runs", "analysis_reports", "change_plans"}
    )


def test_init_is_idempotent(env):
    init_backend_db(get_settings())
    init_backend_db(get_settings())


def test_connection_pragmas(env):
    init_backend_db(get_settings())
    db = open_db(get_settings())
    try:
        assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        db.close()


def test_missing_schema_file_fails_clearly(env, monkeypatch, tmp_path):
    monkeypatch.setenv("DB_SCHEMA_PATH", str(tmp_path / "nope.sql"))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="스키마 파일"):
        init_backend_db(get_settings())


def test_schema_without_backend_zone_fails(env, monkeypatch, tmp_path):
    bad = tmp_path / "bad.sql"
    bad.write_text(
        "-- @db shared\nCREATE TABLE IF NOT EXISTS t (id INTEGER);\n", "utf-8"
    )
    monkeypatch.setenv("DB_SCHEMA_PATH", str(bad))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="@db backend"):
        init_backend_db(get_settings())


def test_split_zones_matches_team_schema(helpers):
    zones = split_zones(helpers.schema.read_text(encoding="utf-8"))
    assert set(zones) == {"shared", "backend"}
    assert "CREATE TABLE IF NOT EXISTS incidents" in zones["shared"]
    assert "CREATE TABLE IF NOT EXISTS users" in zones["backend"]
    assert "CREATE TABLE IF NOT EXISTS incidents" not in zones["backend"]


def test_relative_db_path_is_repo_root_not_cwd(tmp_path, monkeypatch):
    """#75: 상대 DB 경로는 실행 위치(cwd)와 무관하게 저장소 루트 기준."""
    monkeypatch.chdir(tmp_path)
    assert db_file("data/backend.db") == (ROOT / "data" / "backend.db").resolve()
    monkeypatch.chdir(ROOT / "backend")
    assert db_file("data/backend.db") == (ROOT / "data" / "backend.db").resolve()


def test_env_file_is_repo_root():
    """#75: backend/ 에서 실행해도 루트 .env 를 읽는다."""
    assert Settings.model_config["env_file"] == ROOT / ".env"


def test_missing_absolute_db_folder_fails_without_creating(env, monkeypatch, tmp_path):
    """#75: 절대 경로의 부모 폴더가 없으면 빈 DB 를 만들지 않고 경로를 알리며 실패."""
    missing = tmp_path / "nope" / "backend.db"
    monkeypatch.setenv("BACKEND_DB_PATH", str(missing))
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="backend.db 폴더가 없습니다"):
        open_db(get_settings())
    with pytest.raises(RuntimeError, match="nope"):
        init_backend_db(get_settings())
    assert not missing.parent.exists()
