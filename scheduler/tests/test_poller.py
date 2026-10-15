"""Problem 폴링 (FR-SCH-001~005·009, NFR-PERF-002) — ZABBIX_MOCK fixture 로 실 Zabbix 없이."""

import copy
import json
import re
import threading
from datetime import UTC, datetime

import jsonschema
import pytest
from shared_db import SchemaError, find_contract, open_db

from dejafix_scheduler.__main__ import run
from dejafix_scheduler.config import DEFAULT_MOCK_FILE, Settings
from dejafix_scheduler.poller import JOB, poll_once
from dejafix_scheduler.source import (
    MockSource,
    SourceUnavailable,
    UnavailableSource,
    make_source,
)

NOW = datetime(2026, 10, 15, 1, 20, 30, tzinfo=UTC)
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "shared.db", "shared")
    yield c
    c.close()


@pytest.fixture
def data():
    return json.loads(DEFAULT_MOCK_FILE.read_text(encoding="utf-8"))


def rows(conn):
    conn.row_factory = None
    return conn.execute(
        "SELECT zabbix_eventid, status, hostid, host_name, started_at, resolved_at, "
        "severity, tags_json, first_seen_at, last_seen_at FROM incidents ORDER BY zabbix_eventid"
    ).fetchall()


def job(conn):
    return conn.execute(
        "SELECT last_run_at, last_ok_at, status, message FROM scheduler_jobs WHERE job=?",
        (JOB,),
    ).fetchone()


def test_insert_new_problems_with_host_in_same_cycle(conn, data):
    r = poll_once(conn, MockSource(data), NOW)
    assert r.ok and r.inserted == 2
    got = {row[0]: row for row in rows(conn)}
    cpu = got["30001"]
    assert cpu[1] == "problem" and cpu[5] is None
    assert (cpu[2], cpu[3]) == (
        "10001",
        "demo-host",
    )  # FR-SCH-003: 같은 주기에 호스트 채움
    assert cpu[4] == "2026-10-15T01:20:00Z" and cpu[6] == 4
    assert json.loads(cpu[7]) == [{"tag": "scope", "value": "performance"}]
    disk = got["90002"]
    assert disk[1] == "resolved" and disk[5] == "2026-10-15T00:50:00Z"


def test_second_poll_does_not_duplicate(conn, data):
    src = MockSource(data)
    poll_once(conn, src, NOW)
    r = poll_once(conn, src, NOW.replace(second=59))
    assert r.ok and r.inserted == 0
    assert len(rows(conn)) == 2  # FR-SCH-001: 두 번 폴링해도 1행
    assert all(
        row[9] == "2026-10-15T01:20:59Z" for row in rows(conn)
    )  # last_seen_at 갱신
    assert all(
        row[8] == "2026-10-15T01:20:30Z" for row in rows(conn)
    )  # first_seen_at 유지


def test_problem_becomes_resolved(conn, data):
    src = MockSource(data)
    poll_once(conn, src, NOW)
    later = copy.deepcopy(data)
    later["problems"][0]["r_eventid"] = "90020"
    later["problems"][0]["r_clock"] = "1792027500"
    r = poll_once(conn, MockSource(later), NOW)
    assert r.resolved == 1
    cpu = {row[0]: row for row in rows(conn)}["30001"]
    assert cpu[1] == "resolved" and cpu[5] == "2026-10-15T01:25:00Z"  # FR-SCH-002


def test_host_enrich_failure_keeps_row_and_retries(conn, data):
    class NoHosts(MockSource):
        def trigger_hosts(self, triggerids):
            raise SourceUnavailable("trigger.get 실패")

    r = poll_once(conn, NoHosts(data), NOW)
    assert not r.ok  # 보강 실패는 error 로 남긴다
    assert len(rows(conn)) == 2  # 장애 행은 남는다
    assert all(row[2] is None for row in rows(conn))
    r2 = poll_once(conn, MockSource(data), NOW)
    assert r2.ok and r2.enriched == 2
    assert all(row[2] is not None for row in rows(conn))


def test_source_error_does_not_crash_and_recovers(conn, data):
    # FR-SCH-004: Zabbix 중단 → 2주기 error, 프로세스 생존 → 복구 후 ok
    down = UnavailableSource("연결 실패")
    assert not poll_once(conn, down, NOW).ok
    assert not poll_once(conn, down, NOW.replace(second=59)).ok
    last_run, last_ok, status, message = job(conn)
    assert status == "error" and last_ok is None and "연결 실패" in message
    assert last_run == "2026-10-15T01:20:59Z"
    assert poll_once(conn, MockSource(data), NOW.replace(minute=21)).ok
    last_run, last_ok, status, message = job(conn)
    assert status == "ok" and last_ok == "2026-10-15T01:21:30Z" and message is None


def test_last_ok_kept_on_error(conn, data):
    poll_once(conn, MockSource(data), NOW)
    poll_once(conn, UnavailableSource("x"), NOW.replace(minute=21))
    _, last_ok, status, _ = job(conn)
    assert (
        status == "error" and last_ok == "2026-10-15T01:20:30Z"
    )  # 마지막 성공 시각 유지


def test_bad_rows_are_skipped(conn):
    src = MockSource(
        {"problems": [{"eventid": "", "clock": "1"}, {"eventid": "5", "clock": "0"}]}
    )
    r = poll_once(conn, src, NOW)
    assert r.ok and r.inserted == 0 and rows(conn) == []


def test_times_match_incident_schema_pattern(conn, data):
    poll_once(conn, MockSource(data), NOW)
    for row in rows(conn):
        for value in (row[4], row[5], row[8], row[9]):
            assert value is None or ISO.match(value)


def test_rows_map_to_incident_schema(conn, data):
    """Backend 가 이 행을 그대로 옮겼을 때 incident.schema.json 을 통과하는지 (DR-018)."""
    try:
        schema_path = find_contract("incident.schema.json")
    except SchemaError:
        pytest.skip("contracts/incident.schema.json 이 아직 dev 에 없음 (PR #45)")
    poll_once(conn, MockSource(data), NOW)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    labels = ["Not classified", "Information", "Warning", "Average", "High", "Disaster"]
    conn.row_factory = None
    for r in conn.execute(
        "SELECT id, zabbix_eventid, zabbix_triggerid, hostid, host_name, title, severity, "
        "status, started_at, resolved_at, tags_json FROM incidents"
    ):
        inc = {
            "id": r[0],
            "source": "zabbix",
            "zabbix": {"eventid": r[1], "triggerid": r[2], "hostid": r[3]},
            "host": {"id": r[3], "name": r[4]},
            "title": r[5],
            "severity": {"level": r[6], "label": labels[r[6]]},
            "status": r[7],
            "started_at": r[8],
            "resolved_at": r[9],
            "tags": json.loads(r[10]),
            "analysis": {"status": "pending", "report_id": None, "plan_id": None},
        }
        jsonschema.validate(inc, schema)


@pytest.fixture
def no_zabbix_env(monkeypatch):
    """실서버 모드인데 URL·토큰이 비어 있는 상태."""
    monkeypatch.setenv("ZABBIX_MOCK", "false")
    for key in ("ZABBIX_URL", "ZABBIX_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def test_make_source_mock_and_unavailable(no_zabbix_env):
    assert isinstance(make_source(True, DEFAULT_MOCK_FILE), MockSource)
    real = make_source(False, DEFAULT_MOCK_FILE)  # 만들 때는 예외 없이 돌아와야 한다
    # libs/zabbix_ro 미구현이면 SourceUnavailable, 구현 후(PR #64) 설정이 비면 zabbix_ro 오류.
    # 어느 쪽이든 폴링 한 주기가 잡아 error 로 남긴다 (아래 테스트).
    with pytest.raises(Exception):
        real.problems()


def test_real_mode_without_config_keeps_running(conn, no_zabbix_env):
    # FR-SCH-004: 실서버 설정이 비어 있어도 죽지 않고 error 를 남긴 뒤 다음 주기로 간다
    src = make_source(False, DEFAULT_MOCK_FILE)
    r1 = poll_once(conn, src, NOW)
    r2 = poll_once(conn, src, NOW.replace(second=59))
    assert not r1.ok and not r2.ok
    _, last_ok, status, message = job(conn)
    assert status == "error" and last_ok is None and message


def test_run_applies_schema_and_writes_job(tmp_path):
    s = Settings.from_env(
        {"SHARED_DB_PATH": str(tmp_path / "d" / "shared.db"), "ZABBIX_MOCK": "true"}
    )
    assert run(s, threading.Event(), max_cycles=1) == 1
    c = open_db(s.shared_db_path, "shared")
    assert c.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 2
    assert (
        c.execute("SELECT status FROM scheduler_jobs WHERE job=?", (JOB,)).fetchone()[0]
        == "ok"
    )
    c.close()


def test_settings_defaults():
    s = Settings.from_env({})
    assert s.poll_sec == 30 and s.zabbix_mock is False
    assert (
        Settings.from_env({"INCIDENT_POLL_SEC": "1"}).poll_sec == 5
    )  # 너무 짧은 주기 방지
