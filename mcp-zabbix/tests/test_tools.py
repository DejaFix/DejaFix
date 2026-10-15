"""mcp-zabbix 필수 테스트 (mcp-zabbix/CLAUDE.md "테스트", contracts/mcp-tools.md 5장)."""

import asyncio
import json
import time

import pytest
import zabbix_ro
from starlette.testclient import TestClient
from zabbix_ro import ZabbixError

from mcp_zabbix import tools
from mcp_zabbix.envelope import delay_seconds, is_stale, parse_time
from mcp_zabbix.server import REQUIRED_TOOLS, create_server

NOW = 1_792_027_170


class FakeClient:
    """메서드 → 응답(값 또는 예외). 호출 기록을 남긴다."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def call(self, method, params=None):
        self.calls.append((method, params))
        ans = self.answers.get(method, [])
        if isinstance(ans, Exception):
            raise ans
        return ans(params) if callable(ans) else ans


@pytest.fixture
def mock_client():
    return zabbix_ro.from_env({"ZABBIX_MOCK": "true"})


# --- 오래된 값 판정 (SAFE-09, FR-MCP-008) ---
def test_stale_delay_30s_11min_ago():
    assert is_stale(NOW - 11 * 60, "30s", now=NOW) is True


def test_not_stale_2min_ago():
    assert is_stale(NOW - 2 * 60, "30s", now=NOW) is False


def test_stale_uses_delay_x3_when_larger():
    assert is_stale(NOW - 2 * 3600, "1h", now=NOW) is False
    assert is_stale(NOW - 4 * 3600, "1h", now=NOW) is True


def test_stale_when_lastclock_zero_or_missing():
    assert is_stale("0", "1m", now=NOW) is True
    assert is_stale(None, "1m", now=NOW) is True


def test_delay_macro_falls_back_to_600s():
    assert delay_seconds("{$DELAY}") is None
    assert is_stale(NOW - 500, "{$DELAY}", now=NOW) is False


def test_parse_time_iso_and_unix():
    assert parse_time("2026-10-15T00:00:00Z") == parse_time(
        str(parse_time("2026-10-15T00:00:00Z"))
    )
    assert parse_time(123) == 123
    assert parse_time("123") == 123


# --- 크기 제한·오류 봉투 (FR-MCP-007, NFR-PERF-007) ---
def test_items_150_truncated_to_100():
    rows = [
        {
            "itemid": str(i),
            "key_": f"k{i}",
            "lastclock": str(int(time.time())),
            "delay": "1m",
        }
        for i in range(150)
    ]
    client = FakeClient({"item.get": lambda p: rows[: p["limit"]]})
    out = tools.list_items(client, "1")
    assert out["ok"] is True
    assert len(out["data"]) == 100
    assert out["truncated"] is True
    assert out["data"][0]["stale"] is False


def test_zabbix_5xx_becomes_zabbix_error_without_stack():
    client = FakeClient({"problem.get": ZabbixError("HTTP 502 Bad Gateway")})
    out = tools.list_problems(client)
    assert out == {
        "ok": False,
        "collected_at": out["collected_at"],
        "reason": "ZABBIX_ERROR",
        "message": "Zabbix 조회 실패",
    }
    assert "Traceback" not in json.dumps(out)


def test_permission_error_is_no_permission():
    client = FakeClient(
        {
            "host.get": ZabbixError(
                "Application error.",
                code=-32500,
                data="No permissions to referred object or it does not exist!",
            )
        }
    )
    assert tools.get_host(client, "1")["reason"] == "NO_PERMISSION"


def test_unknown_eventid_not_found(mock_client):
    out = tools.get_problem(mock_client, "999999")
    assert out["ok"] is False and out["reason"] == "NOT_FOUND"


# --- 도구 5개 (fixture, FR-MCP-010) ---
def test_list_problems_adds_host(mock_client):
    out = tools.list_problems(mock_client)
    assert out["ok"] is True and out["data"]
    p = out["data"][0]
    assert set(p) == {
        "eventid",
        "objectid",
        "name",
        "severity",
        "clock",
        "host",
        "tags",
    }
    assert p["host"]["hostid"] and p["host"]["name"]


def test_get_problem_has_trigger_items(mock_client):
    eventid = tools.list_problems(mock_client)["data"][0]["eventid"]
    out = tools.get_problem(mock_client, eventid)
    assert out["ok"] is True
    data = out["data"]
    assert data["items"] and data["items"] == data["trigger"]["items"]
    assert set(data["items"][0]) == {"itemid", "key_", "name", "value_type", "units"}
    assert data["hosts"]


def test_get_host_has_no_address(mock_client):
    hostid = tools.list_problems(mock_client)["data"][0]["host"]["hostid"]
    out = tools.get_host(mock_client, hostid)
    assert out["ok"] is True
    assert isinstance(out["data"]["in_maintenance"], bool)
    text = json.dumps(out)
    assert '"ip"' not in text and '"dns"' not in text


def test_list_items_values_are_strings(mock_client):
    hostid = tools.list_problems(mock_client)["data"][0]["host"]["hostid"]
    out = tools.list_items(mock_client, hostid)
    assert out["ok"] is True and out["data"]
    item = out["data"][0]
    assert isinstance(item["lastclock"], str) and isinstance(item["stale"], bool)


def test_get_history_points(mock_client):
    eventid = tools.list_problems(mock_client)["data"][0]["eventid"]
    itemid = tools.get_problem(mock_client, eventid)["data"]["items"][0]["itemid"]
    out = tools.get_history(mock_client, itemid, NOW - 3600, NOW, now=NOW)
    assert out["ok"] is True
    data = out["data"]
    assert data["source"] == "history" and data["itemid"] == itemid
    clocks = [int(p["clock"]) for p in data["points"]]
    assert clocks == sorted(clocks)


def test_get_history_over_24h_uses_trend():
    client = FakeClient(
        {
            "item.get": [
                {"itemid": "5", "value_type": "0", "delay": "1m", "lastclock": str(NOW)}
            ],
            "trend.get": [
                {"itemid": "5", "clock": str(NOW - 3600), "value_avg": "12.5"}
            ],
        }
    )
    out = tools.get_history(client, "5", NOW - 2 * 86400, NOW, now=NOW)
    assert out["data"]["source"] == "trend"
    assert out["data"]["points"] == [{"clock": str(NOW - 3600), "value": "12.5"}]
    assert [m for m, _ in client.calls] == ["item.get", "trend.get"]


def test_get_history_limit_keeps_latest():
    rows = [
        {"itemid": "5", "clock": str(NOW - i * 60), "value": str(i)} for i in range(600)
    ]
    client = FakeClient(
        {
            "item.get": [
                {"itemid": "5", "value_type": "0", "delay": "1m", "lastclock": str(NOW)}
            ],
            "history.get": rows,
        }
    )
    out = tools.get_history(client, "5", NOW - 3600, NOW, now=NOW)
    pts = out["data"]["points"]
    assert len(pts) == 500 and out["truncated"] is True
    assert pts[-1]["clock"] == str(NOW) and out["data"]["stale"] is False


def test_only_get_methods_are_called(mock_client):
    client = FakeClient({})
    tools.list_problems(client)
    tools.get_host(client, "1")
    tools.list_items(client, "1")
    assert all(m.endswith(".get") for m, _ in client.calls)


# --- 서버: 등록 도구·봉투·healthz (FR-MCP-009, SAFE-03, FR-INF-002) ---
def test_tools_list_is_exactly_required_five(mock_client):
    server = create_server(mock_client)
    names = sorted(t.name for t in asyncio.run(server.list_tools()))
    assert names == sorted(REQUIRED_TOOLS)
    for name in names:
        assert not any(
            w in name for w in ("create", "update", "delete", "execute", "set")
        )


def test_call_tool_returns_structured_envelope(mock_client):
    server = create_server(mock_client)
    result = asyncio.run(server.call_tool("zabbix_list_problems", {}))
    content, structured = result
    assert structured["ok"] is True and "collected_at" in structured
    assert json.loads(content[0].text) == structured


def test_healthz_mock(mock_client):
    app = create_server(mock_client).streamable_http_app()
    with TestClient(app) as http:
        resp = http.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "zabbix": "mock"}


def test_healthz_down_when_zabbix_unreachable():
    client = FakeClient({"apiinfo.version": ZabbixError("connect failed")})
    app = create_server(client, mock=False).streamable_http_app()
    with TestClient(app) as http:
        assert http.get("/healthz").json() == {"ok": True, "zabbix": "down"}
