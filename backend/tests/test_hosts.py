"""API 7번 감시 호스트 목록 — 에이전트 가용성으로 up·down·unknown, 열린 Problem 수 (contracts/api.md #7).

장애가 없다고 up 으로 보지 않는다(SAFE-08·09). Zabbix 가 끊기면 503 ZABBIX_UNAVAILABLE.
"""

import threading
from datetime import datetime, timezone

import pytest

import zabbix_ro
from dejafix_backend import zabbix
from dejafix_backend.routers.dashboard import get_now
from dejafix_backend.routers.hosts import state_of

NOW = datetime(2026, 11, 25, 8, 0, 0, tzinfo=timezone.utc)


class FakeZabbix:
    hosts: list = []
    problems: list = []
    triggers: list = []
    error: Exception | None = None
    calls: list = []
    lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, method, params):
        with FakeZabbix.lock:
            FakeZabbix.calls.append((method, dict(params)))
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
    FakeZabbix.error, FakeZabbix.calls = None, []
    zabbix.reset()
    monkeypatch.setattr(zabbix, "build_client", lambda settings: FakeZabbix())
    yield FakeZabbix
    zabbix.reset()


def host(hostid, name, active="0", agent=None, status="0"):
    interfaces = [] if agent is None else [{"type": "1", "available": agent}]
    return {
        "hostid": hostid,
        "host": f"h{hostid}",
        "name": name,
        "status": status,
        "active_available": active,
        "interfaces": interfaces,
    }


def get_hosts(make_client, helpers):
    client = make_client()
    client.app.dependency_overrides[get_now] = lambda: NOW
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    return client.get("/api/hosts", headers=headers)


def test_state_comes_from_agent_availability_not_from_problems(make_client, helpers):
    FakeZabbix.hosts = [
        host("1", "web-01", active="1"),  # 액티브 에이전트 응답
        host("2", "db-01", active="0", agent="2"),  # 패시브 에이전트 사용 불가
        host("3", "office-pc-07"),  # 가용성 모름 → unknown (장애 없어도 up 아님)
        host("4", "api-01", active="2", agent="1"),  # 하나라도 1 이면 up
        host("5", "off-01", active="1", status="1"),  # 감시 안 함 → 목록에 없음
    ]
    FakeZabbix.problems = [
        {"eventid": "10", "objectid": "100", "r_eventid": "0"},
        {"eventid": "11", "objectid": "100", "r_eventid": "0"},
        {"eventid": "12", "objectid": "101", "r_eventid": "55"},  # 해결됨
    ]
    FakeZabbix.triggers = [{"triggerid": "100", "hosts": [{"hostid": "2"}]}]
    res = get_hosts(make_client, helpers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["data"] == [
        {"id": "4", "name": "api-01", "state": "up", "problems": 0},
        {"id": "2", "name": "db-01", "state": "down", "problems": 2},
        {"id": "3", "name": "office-pc-07", "state": "unknown", "problems": 0},
        {"id": "1", "name": "web-01", "state": "up", "problems": 0},
    ]
    assert body["meta"] == {"collected_at": "2026-11-25T08:00:00Z", "truncated": False}


def test_only_read_methods_are_called(make_client, helpers):
    FakeZabbix.hosts = [host("1", "web-01", active="1")]
    get_hosts(make_client, helpers)
    assert {m for m, _ in FakeZabbix.calls} <= {
        "host.get",
        "problem.get",
        "trigger.get",
    }
    host_call = next(p for m, p in FakeZabbix.calls if m == "host.get")
    assert host_call["filter"] == {"status": "0"}


def test_zabbix_down_is_503(make_client, helpers):
    FakeZabbix.error = zabbix_ro.ZabbixError("down")
    res = get_hosts(make_client, helpers)
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "ZABBIX_UNAVAILABLE"


def test_needs_login(make_client):
    assert make_client().get("/api/hosts").status_code == 401


@pytest.mark.parametrize(
    ("raw", "state"),
    [
        ({"active_available": "1"}, "up"),
        ({"active_available": "2"}, "down"),
        ({"active_available": "0"}, "unknown"),
        ({}, "unknown"),
        (
            {"active_available": "0", "interfaces": [{"type": "2", "available": "1"}]},
            "unknown",
        ),
    ],
)
def test_state_of(raw, state):
    assert state_of(raw) == state


def test_more_than_max_hosts_is_truncated(make_client, helpers, monkeypatch):
    from dejafix_backend.routers import hosts as hosts_router

    monkeypatch.setattr(hosts_router, "MAX_HOSTS", 2)
    FakeZabbix.hosts = [host(str(i), f"pc-{i}", active="1") for i in range(3)]
    res = get_hosts(make_client, helpers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [r["name"] for r in body["data"]] == ["pc-0", "pc-1"]
    assert body["meta"]["truncated"] is True
