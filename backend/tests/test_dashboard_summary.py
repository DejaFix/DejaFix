"""API 5번 대시보드 요약 — shared.db 집계 + Zabbix 호스트 집계, 모두 Measured, Zabbix 가 끊겨도 shared 쪽은 유지 (FR-BE-005)."""

import sqlite3
import threading
import time
from datetime import datetime, timezone

import pytest

import zabbix_ro
from dejafix_backend import zabbix
from dejafix_backend.db import split_zones
from dejafix_backend.routers.dashboard import get_now, kst_today_window

NOW = datetime(2026, 10, 15, 3, 0, 0, tzinfo=timezone.utc)  # KST 2026-10-15 12:00
NOW_ISO = "2026-10-15T03:00:00Z"


class FakeZabbix:
    """호스트·문제·트리거를 정해 주는 zabbix_ro 클라이언트 대역."""

    hosts: list = []
    problems: list = []
    triggers: list = []
    error: Exception | None = None
    delay = 0.0
    calls: list = []
    lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, method, params):
        with FakeZabbix.lock:
            FakeZabbix.calls.append((method, dict(params)))
        if FakeZabbix.delay:
            time.sleep(FakeZabbix.delay)
        if FakeZabbix.error is not None:
            raise FakeZabbix.error
        return {
            "host.get": FakeZabbix.hosts,
            "problem.get": FakeZabbix.problems,
            "trigger.get": FakeZabbix.triggers,
        }[method]


@pytest.fixture(autouse=True)
def fake_zabbix(monkeypatch):
    FakeZabbix.hosts, FakeZabbix.problems, FakeZabbix.triggers = [], [], []
    FakeZabbix.error, FakeZabbix.delay, FakeZabbix.calls = None, 0.0, []
    zabbix.reset()
    monkeypatch.setattr(zabbix, "build_client", lambda settings: FakeZabbix())
    yield FakeZabbix
    zabbix.reset()


def host(hostid, available, status="0"):
    return {"hostid": hostid, "status": status, "active_available": available}


def create_shared(helpers, path, incidents=(), runs=(), reports=()):
    """스키마만 있는 shared.db 에 필요한 행만 넣는다 (시드 장애 6건을 쓰지 않는다)."""
    schema = split_zones(helpers.schema.read_text(encoding="utf-8"))["shared"]
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    for number, (severity, status) in enumerate(incidents, start=1):
        conn.execute(
            "INSERT INTO incidents (zabbix_eventid, zabbix_triggerid, title, severity, status,"
            " started_at, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(number), str(number), f"장애 {number}", severity, status)
            + (NOW_ISO,) * 3,
        )
    for number, (kind, started, finished) in enumerate(runs, start=1):
        conn.execute(
            "INSERT INTO agent_runs (id, kind, incident_id, caller, status, model, started_at, finished_at)"
            " VALUES (?, ?, 1, 'worker', 'done', NULL, ?, ?)",
            (f"r{number}", kind, started, finished),
        )
    for number, created in enumerate(reports, start=1):
        conn.execute(
            "INSERT INTO analysis_reports (id, incident_id, run_id, version, kind, summary, created_at)"
            " VALUES (?, 1, 'r1', ?, 'fallback', '요약', ?)",
            (number, number, created),
        )
    conn.commit()
    conn.close()


def summary(make_client, helpers, **env):
    client = make_client(**env)
    client.app.dependency_overrides[get_now] = lambda: NOW
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    response = client.get("/api/dashboard/summary", headers=headers)
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------- KST 오늘 범위


def test_kst_window_is_midnight_to_midnight_in_utc():
    assert kst_today_window(NOW) == ("2026-10-14T15:00:00Z", "2026-10-15T15:00:00Z")
    just_before = datetime(
        2026, 10, 14, 14, 59, 59, tzinfo=timezone.utc
    )  # KST 10/14 23:59:59
    assert kst_today_window(just_before) == (
        "2026-10-13T15:00:00Z",
        "2026-10-14T15:00:00Z",
    )
    midnight = datetime(
        2026, 10, 14, 15, 0, 0, tzinfo=timezone.utc
    )  # KST 10/15 00:00:00
    assert kst_today_window(midnight) == (
        "2026-10-14T15:00:00Z",
        "2026-10-15T15:00:00Z",
    )


# ---------------------------------------------------------------- shared.db 집계


def test_active_and_high_counts(make_client, env, helpers):
    create_shared(
        helpers,
        env.shared,
        incidents=[
            (5, "problem"),
            (4, "problem"),
            (3, "problem"),
            (1, "problem"),
            (5, "resolved"),
        ],
    )
    data = summary(make_client, helpers)["data"]
    assert data["active_incidents"]["value"] == 4  # 해결된 장애(5번째)는 빠진다
    assert data["high_incidents"]["value"] == 2  # severity 4·5 (해결된 5는 빠진다)
    assert data["active_incidents"]["unit"] == data["high_incidents"]["unit"] == "건"


def test_reports_today_uses_the_kst_day_boundaries(make_client, env, helpers):
    create_shared(
        helpers,
        env.shared,
        incidents=[(4, "problem")],
        runs=[("analyze", NOW_ISO, NOW_ISO)],
        reports=[
            "2026-10-14T14:59:59Z",  # KST 어제 23:59:59 → 제외
            "2026-10-14T15:00:00Z",  # KST 오늘 00:00:00 → 포함
            "2026-10-15T14:59:59Z",  # KST 오늘 23:59:59 → 포함
            "2026-10-15T15:00:00Z",  # KST 내일 00:00:00 → 제외
        ],
    )
    assert summary(make_client, helpers)["data"]["reports_today"]["value"] == 2


def test_average_analysis_time_counts_only_todays_finished_analyze_runs(
    make_client, env, helpers
):
    create_shared(
        helpers,
        env.shared,
        incidents=[(4, "problem")],
        runs=[
            ("analyze", "2026-10-15T01:00:00Z", "2026-10-15T01:00:30Z"),  # 30초
            ("analyze", "2026-10-15T02:00:00Z", "2026-10-15T02:01:30Z"),  # 90초
            (
                "analyze",
                "2026-10-14T14:00:00Z",
                "2026-10-14T14:10:00Z",
            ),  # 어제(KST) → 제외
            ("analyze", "2026-10-15T02:30:00Z", None),  # 아직 안 끝남 → 제외
            ("chat", "2026-10-15T02:40:00Z", "2026-10-15T02:50:00Z"),  # 채팅 → 제외
        ],
    )
    avg = summary(make_client, helpers)["data"]["avg_analysis_sec"]
    assert avg == {
        "value": 60.0,
        "unit": "s",
        "collected_at": NOW_ISO,
        "unknown": False,
    }


def test_no_finished_run_today_is_unknown_not_zero(make_client, env, helpers):
    create_shared(helpers, env.shared, incidents=[(4, "problem")])
    data = summary(make_client, helpers)["data"]
    assert data["avg_analysis_sec"]["value"] is None
    assert data["avg_analysis_sec"]["unknown"] is True
    assert data["avg_analysis_sec"]["unknown_reason"] == "NO_DATA"
    assert (
        data["reports_today"]["value"] == 0
        and data["reports_today"]["unknown"] is False
    )  # 0건은 실제 값


@pytest.mark.safety_regression
def test_shared_db_not_there_yet_is_unknown_no_data_but_hosts_still_work(
    make_client, helpers, fake_zabbix
):
    fake_zabbix.hosts = [host("1", "1"), host("2", "0")]
    data = summary(make_client, helpers)["data"]  # shared.db 파일이 없다
    for name in (
        "active_incidents",
        "high_incidents",
        "reports_today",
        "avg_analysis_sec",
    ):
        assert (
            data[name]["value"] is None and data[name]["unknown_reason"] == "NO_DATA"
        ), name
    assert data["hosts"]["total"]["value"] == 2


# ---------------------------------------------------------------- Zabbix 호스트 집계


def test_host_counts_follow_the_documented_definition(
    make_client, env, helpers, fake_zabbix
):
    fake_zabbix.hosts = [
        host("1", "1"),  # 가용 + 활성 문제 없음 → 정상
        host("2", "1"),  # 가용이지만 활성 문제 있음 → 정상 아님
        host("3", "0"),  # 가용성 알 수 없음 → 확인 불가
        host("4", "2"),  # 사용 불가 → total 에만
        host("5", "1", status="1"),  # 감시 중지(비활성) → 제외
        host("6", "1"),  # 해결된 문제만 있음 → 정상
    ]
    fake_zabbix.problems = [
        {"eventid": "10", "objectid": "100", "r_eventid": "0"},  # 활성 → 호스트 2
        {
            "eventid": "11",
            "objectid": "101",
            "r_eventid": "55",
        },  # 해결됨 → 호스트 6 은 정상
    ]
    fake_zabbix.triggers = [{"triggerid": "100", "hosts": [{"hostid": "2"}]}]
    create_shared(helpers, env.shared)
    hosts = summary(make_client, helpers)["data"]["hosts"]
    assert hosts["total"]["value"] == 5  # 1,2,3,4,6 (5는 감시 중지)
    assert hosts["ok"]["value"] == 2  # 1, 6
    assert hosts["unknown"]["value"] == 1  # 3
    assert all(hosts[k]["unit"] == "대" and hosts[k]["unknown"] is False for k in hosts)
    # 해결된 문제의 트리거는 조회하지 않았다(활성 문제의 트리거만)
    trigger_call = next(p for m, p in fake_zabbix.calls if m == "trigger.get")
    assert trigger_call["triggerids"] == ["100"]


def test_trigger_lookup_is_skipped_when_there_is_no_active_problem(
    make_client, env, helpers, fake_zabbix
):
    fake_zabbix.hosts = [host("1", "1")]
    fake_zabbix.problems = [{"eventid": "11", "objectid": "101", "r_eventid": "55"}]
    create_shared(helpers, env.shared)
    hosts = summary(make_client, helpers)["data"]["hosts"]
    assert (hosts["total"]["value"], hosts["ok"]["value"]) == (1, 1)
    assert "trigger.get" not in [m for m, _ in fake_zabbix.calls]


@pytest.mark.safety_regression
def test_zabbix_down_makes_only_host_kpis_unknown(
    make_client, env, helpers, fake_zabbix
):
    """계약: Zabbix 가 끊기면 hosts.* 는 unknown:true·TOOL_ERROR, shared.db 기준 KPI 는 값을 유지한다."""
    fake_zabbix.error = zabbix_ro.ZabbixError(
        "Zabbix 연결 실패: host.get (ConnectError)"
    )
    create_shared(
        helpers,
        env.shared,
        incidents=[(5, "problem"), (3, "problem")],
        runs=[("analyze", "2026-10-15T01:00:00Z", "2026-10-15T01:00:40Z")],
        reports=["2026-10-15T01:00:40Z"],
    )
    body = summary(make_client, helpers)
    data = body["data"]
    for name in ("ok", "total", "unknown"):
        item = data["hosts"][name]
        assert item["value"] is None and item["unknown"] is True, name
        assert item["unknown_reason"] == "TOOL_ERROR", name
    # shared.db 기준 KPI 는 그대로
    assert (
        data["active_incidents"]["value"] == 2 and data["high_incidents"]["value"] == 1
    )
    assert (
        data["reports_today"]["value"] == 1
        and data["avg_analysis_sec"]["value"] == 40.0
    )
    assert "연결 실패" not in str(body) and "ConnectError" not in str(
        body
    )  # 오류 내용은 응답에 없다


def test_slow_zabbix_is_cut_off_and_the_rest_still_answers(
    make_client, env, helpers, fake_zabbix
):
    fake_zabbix.delay = 1.5
    fake_zabbix.hosts = [host("1", "1")]
    create_shared(helpers, env.shared, incidents=[(4, "problem")])
    # 실서버 모드여야 타임아웃·스레드 경로(안전장치)를 탄다. 목 모드는 즉시 답하므로 그 경로를 거치지 않는다.
    client = make_client(
        ZABBIX_MOCK="false",
        ZABBIX_URL="http://zabbix.invalid/x",
        ZABBIX_API_TOKEN="t",
        ZABBIX_TIMEOUT_SEC="0.3",
    )
    client.app.dependency_overrides[get_now] = lambda: NOW
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    started = time.monotonic()  # 앱 기동·로그인 시간은 빼고 요청 하나만 잰다
    response = client.get("/api/dashboard/summary", headers=headers)
    elapsed = time.monotonic() - started
    data = response.json()["data"]
    assert response.status_code == 200
    assert (
        elapsed < 1.0
    )  # 1.5초 걸리는 Zabbix 를 기다리지 않고 한도(0.3초) 근처에서 답했다
    assert data["hosts"]["total"]["unknown_reason"] == "TOOL_ERROR"
    assert data["active_incidents"]["value"] == 1  # shared 쪽은 정상


def test_unexpected_zabbix_payload_is_isolated_too(
    make_client, env, helpers, fake_zabbix
):
    fake_zabbix.hosts = [
        {"status": "0", "active_available": "1"}
    ]  # hostid 가 없는 이상한 응답
    create_shared(helpers, env.shared)
    data = summary(make_client, helpers)["data"]
    assert data["hosts"]["total"]["unknown_reason"] == "TOOL_ERROR"


def test_zabbix_results_are_cached_across_requests_in_real_mode(
    make_client, env, helpers, fake_zabbix
):
    """화면이 15초마다 불러도 5초 안의 요청은 Zabbix 를 다시 부르지 않는다(A2 안전장치)."""
    fake_zabbix.hosts = [host("1", "1")]
    create_shared(helpers, env.shared)
    client = make_client(
        ZABBIX_MOCK="false", ZABBIX_URL="http://zabbix.invalid/x", ZABBIX_API_TOKEN="t"
    )
    client.app.dependency_overrides[get_now] = lambda: NOW
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    for _ in range(3):
        assert client.get("/api/dashboard/summary", headers=headers).status_code == 200
    assert [m for m, _ in fake_zabbix.calls].count("host.get") == 1


# ---------------------------------------------------------------- 계약 모양


def test_response_has_exactly_the_documented_shape(
    make_client, env, helpers, fake_zabbix
):
    fake_zabbix.hosts = [host("1", "1")]
    create_shared(helpers, env.shared, incidents=[(4, "problem")])
    body = summary(make_client, helpers)
    assert set(body) == {"data", "meta"}
    assert body["meta"] == {"generated_at": NOW_ISO}
    data = body["data"]
    assert set(data) == {
        "active_incidents",
        "high_incidents",
        "hosts",
        "reports_today",
        "avg_analysis_sec",
        "llm_usage_today",
    }
    assert set(data["hosts"]) == {"ok", "total", "unknown"}
    assert data["llm_usage_today"] is None  # [선택] — 필수 단계에서는 null
    measured_items = [
        data[k]
        for k in (
            "active_incidents",
            "high_incidents",
            "reports_today",
            "avg_analysis_sec",
        )
    ]
    measured_items += list(data["hosts"].values())
    for item in measured_items:
        assert {"value", "unit", "collected_at", "unknown"} <= set(item)
        assert item["collected_at"] == NOW_ISO
        if item["unknown"]:
            assert item["value"] is None and item["unknown_reason"] in {
                "NO_DATA",
                "STALE",
                "TOOL_ERROR",
                "NO_PERMISSION",
                "NOT_COLLECTED",
            }
        else:
            assert (
                isinstance(item["value"], (int, float)) and "unknown_reason" not in item
            )


def test_requires_login(client):
    assert client.get("/api/dashboard/summary").status_code == 401
