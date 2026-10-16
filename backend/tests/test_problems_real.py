"""API 6번 실시간 문제 목록 — problem.get + trigger.get(selectHosts), 해결된 문제 제외, incident_id 매칭, 503 (FR-BE-006)."""

import sqlite3
import threading
import time
from datetime import datetime, timezone

import pytest

from dejafix_backend import zabbix
from dejafix_backend.db import split_zones
from dejafix_backend.routers.dashboard import get_now
from dejafix_backend.routers.problems import MAX_PROBLEMS

NOW = datetime(2026, 10, 15, 3, 0, 0, tzinfo=timezone.utc)
NOW_ISO = "2026-10-15T03:00:00Z"
# 2026-10-15T01:20:00Z
CLOCK_0120 = "1792027200"
CLOCK_0100 = str(int(CLOCK_0120) - 1200)


class FakeZabbix:
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
        return {"problem.get": FakeZabbix.problems, "trigger.get": FakeZabbix.triggers}[
            method
        ]


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeZabbix.problems, FakeZabbix.triggers = [], []
    FakeZabbix.error, FakeZabbix.delay, FakeZabbix.calls = None, 0.0, []
    zabbix.reset()
    monkeypatch.setattr(zabbix, "build_client", lambda settings: FakeZabbix())
    yield FakeZabbix
    zabbix.reset()


def problem(
    eventid,
    objectid="100",
    severity="4",
    clock=CLOCK_0120,
    r_eventid="0",
    tags=None,
    name=None,
):
    return {
        "eventid": str(eventid),
        "objectid": objectid,
        "name": name or f"문제 {eventid}",
        "severity": severity,
        "clock": clock,
        "r_eventid": r_eventid,
        "tags": tags if tags is not None else [],
    }


def trigger(triggerid, hostid, name):
    return {
        "triggerid": triggerid,
        "hosts": [{"hostid": hostid, "host": name + "-tech", "name": name}],
    }


def create_shared(helpers, path, eventids=()):
    schema = split_zones(helpers.schema.read_text(encoding="utf-8"))["shared"]
    conn = sqlite3.connect(path)
    conn.executescript(schema)
    for incident_id, eventid in eventids:
        conn.execute(
            "INSERT INTO incidents (id, zabbix_eventid, zabbix_triggerid, title, severity, status,"
            " started_at, first_seen_at, last_seen_at) VALUES (?, ?, '1', 't', 4, 'problem', ?, ?, ?)",
            (incident_id, eventid, NOW_ISO, NOW_ISO, NOW_ISO),
        )
    conn.commit()
    conn.close()


def get(make_client, helpers, query="", **env):
    client = make_client(**env)
    client.app.dependency_overrides[get_now] = lambda: NOW
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    return client.get(f"/api/problems{query}", headers=headers)


# ---------------------------------------------------------------- 매핑


def test_fields_are_mapped_to_the_contract_shape(make_client, env, helpers, fake):
    fake.problems = [
        problem(
            40211,
            objectid="100",
            severity="4",
            tags=[
                {"tag": "component", "value": "storage"},
                {"tag": "scope", "value": "capacity"},
            ],
            name="Disk space is critically low",
        )
    ]
    fake.triggers = [trigger("100", "10584", "LAB-PC-07")]
    create_shared(helpers, env.shared, eventids=[(12, "40211")])
    body = get(make_client, helpers).json()
    assert body["data"] == [
        {
            "eventid": "40211",
            "name": "Disk space is critically low",
            "severity": {"level": 4, "label": "High"},
            "clock": "2026-10-15T01:20:00Z",
            "host": {"id": "10584", "name": "LAB-PC-07"},
            "tags": [
                {"tag": "component", "value": "storage"},
                {"tag": "scope", "value": "capacity"},
            ],
            "incident_id": 12,
        }
    ]
    assert body["meta"] == {"collected_at": NOW_ISO, "truncated": False}


@pytest.mark.parametrize(
    "severity,label",
    [
        ("0", "Not classified"),
        ("1", "Information"),
        ("2", "Warning"),
        ("3", "Average"),
        ("4", "High"),
        ("5", "Disaster"),
    ],
)
def test_severity_labels(make_client, env, helpers, fake, severity, label):
    fake.problems = [problem(1, severity=severity)]
    fake.triggers = [trigger("100", "1", "H")]
    create_shared(helpers, env.shared)
    assert get(make_client, helpers).json()["data"][0]["severity"] == {
        "level": int(severity),
        "label": label,
    }


def test_newest_first_and_resolved_problems_are_excluded(
    make_client, env, helpers, fake
):
    fake.problems = [
        problem(10, clock=CLOCK_0100),
        problem(11, clock=CLOCK_0120),
        problem(12, clock=CLOCK_0120, r_eventid="55"),  # 해결됨 → 제외
        problem(13, clock=CLOCK_0120),  # 같은 시각이면 eventid 큰 것 먼저
    ]
    fake.triggers = [trigger("100", "1", "H")]
    create_shared(helpers, env.shared)
    assert [p["eventid"] for p in get(make_client, helpers).json()["data"]] == [
        "13",
        "11",
        "10",
    ]


def test_incident_id_is_null_when_not_collected_yet_or_shared_db_is_missing(
    make_client, env, helpers, fake
):
    fake.problems = [problem(1), problem(2)]
    fake.triggers = [trigger("100", "1", "H")]
    create_shared(helpers, env.shared, eventids=[(7, "1")])  # 2번 문제는 아직 수집 전
    ids = {
        p["eventid"]: p["incident_id"] for p in get(make_client, helpers).json()["data"]
    }
    assert ids == {"1": 7, "2": None}


@pytest.mark.safety_regression
def test_shared_db_not_there_yet_gives_null_incident_ids_not_an_error(
    make_client, helpers, fake
):
    fake.problems = [problem(1)]
    fake.triggers = [trigger("100", "1", "H")]
    response = get(make_client, helpers)  # shared.db 파일 없음
    assert response.status_code == 200
    assert response.json()["data"][0]["incident_id"] is None


def test_unknown_host_is_null_not_an_empty_string(make_client, env, helpers, fake):
    fake.problems = [problem(1, objectid="999")]
    fake.triggers = []  # 트리거를 찾을 수 없다
    create_shared(helpers, env.shared)
    assert get(make_client, helpers).json()["data"][0]["host"] == {
        "id": None,
        "name": None,
    }


# ---------------------------------------------------------------- 필터


def test_severity_min_filters_and_is_sent_to_zabbix(make_client, env, helpers, fake):
    fake.problems = [
        problem(1, severity="5"),
        problem(2, severity="4"),
        problem(3, severity="3"),
    ]
    fake.triggers = [trigger("100", "1", "H")]
    create_shared(helpers, env.shared)
    data = get(make_client, helpers, "?severity_min=4").json()["data"]
    assert {p["eventid"] for p in data} == {
        "1",
        "2",
    }  # Zabbix 가 걸러 주지 못해도 여기서 한 번 더
    sent = next(p for m, p in fake.calls if m == "problem.get")
    assert sent["severities"] == [4, 5]


def test_hostid_filters_and_is_sent_to_zabbix(make_client, env, helpers, fake):
    fake.problems = [problem(1, objectid="100"), problem(2, objectid="200")]
    fake.triggers = [trigger("100", "10584", "A"), trigger("200", "10585", "B")]
    create_shared(helpers, env.shared)
    data = get(make_client, helpers, "?hostid=10585").json()["data"]
    assert [p["eventid"] for p in data] == ["2"]
    sent = next(p for m, p in fake.calls if m == "problem.get")
    assert sent["hostids"] == ["10585"]


def test_bad_severity_min_is_422(make_client, env, helpers):
    create_shared(helpers, env.shared)
    assert get(make_client, helpers, "?severity_min=9").status_code == 422


# ---------------------------------------------------------------- 잘림


@pytest.mark.parametrize(
    "count,truncated", [(MAX_PROBLEMS, False), (MAX_PROBLEMS + 1, True)]
)
def test_truncated_flag(make_client, env, helpers, fake, count, truncated):
    fake.problems = [
        problem(i, clock=str(int(CLOCK_0100) + i)) for i in range(1, count + 1)
    ]
    fake.triggers = [trigger("100", "1", "H")]
    create_shared(helpers, env.shared)
    body = get(make_client, helpers).json()
    assert len(body["data"]) == MAX_PROBLEMS
    assert body["meta"]["truncated"] is truncated


# ---------------------------------------------------------------- Zabbix 실패 → 503


@pytest.mark.safety_regression
def test_zabbix_down_is_503_with_the_documented_code_and_no_details(
    make_client, env, helpers, fake
):
    import zabbix_ro

    fake.error = zabbix_ro.ZabbixError(
        "Zabbix 연결 실패: problem.get (ConnectError) secret-detail"
    )
    create_shared(helpers, env.shared)
    response = get(make_client, helpers)
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "ZABBIX_UNAVAILABLE",
            "message": "Zabbix에 연결할 수 없습니다",
        }
    }
    assert "secret-detail" not in response.text


def test_slow_zabbix_is_503_within_the_time_limit(make_client, env, helpers, fake):
    fake.delay = 1.5
    fake.problems = [problem(1)]
    create_shared(helpers, env.shared)
    client = make_client(
        ZABBIX_MOCK="false",
        ZABBIX_URL="http://zabbix.invalid/x",
        ZABBIX_API_TOKEN="t",
        ZABBIX_TIMEOUT_SEC="0.3",
    )
    client.app.dependency_overrides[get_now] = lambda: NOW
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    started = time.monotonic()
    response = client.get("/api/problems", headers=headers)
    assert time.monotonic() - started < 1.0
    assert (
        response.status_code == 503
        and response.json()["error"]["code"] == "ZABBIX_UNAVAILABLE"
    )


def test_malformed_zabbix_payload_is_503_not_500(make_client, env, helpers, fake):
    fake.problems = [{"eventid": "1", "objectid": "100"}]  # severity·clock 없음
    create_shared(helpers, env.shared)
    assert get(make_client, helpers).status_code == 503


# ---------------------------------------------------------------- 호출 범위


@pytest.mark.safety_regression
def test_only_the_two_read_methods_are_used_and_trigger_lookup_is_skipped_when_empty(
    make_client, env, helpers, fake
):
    fake.problems = []
    create_shared(helpers, env.shared)
    body = get(make_client, helpers).json()
    assert body["data"] == [] and body["meta"]["truncated"] is False
    assert [m for m, _ in fake.calls] == [
        "problem.get"
    ]  # 문제가 없으면 trigger.get 은 부르지 않는다

    zabbix.reset()
    fake.calls.clear()
    fake.problems = [problem(1)]
    fake.triggers = [trigger("100", "1", "H")]
    get(make_client, helpers)
    assert {m for m, _ in fake.calls} == {"problem.get", "trigger.get"}


def test_requires_login(client):
    assert client.get("/api/problems").status_code == 401
