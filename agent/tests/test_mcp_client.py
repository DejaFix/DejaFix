"""실 MCP 클라이언트 (T47, FR-AG-010, SAFE-03). 네트워크 없이 MCPServer 를 프로세스 안에서 붙인다."""

import asyncio
import contextlib
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.mcpserver import MCPServer

from dejafix_agent.config import Settings
from dejafix_agent.main import create_app, make_tool_client
from dejafix_agent.mcp_client import McpToolClient, envelope_of, startup_check
from dejafix_agent.tools import ForbiddenToolError, UnavailableToolClient

ENVELOPE = {
    "ok": True,
    "collected_at": "2026-10-15T01:00:00Z",
    "data": {"eventid": "1", "items": [{"itemid": "9", "key_": "k"}]},
    "truncated": False,
}


def _server(extra_tool: str | None = None) -> MCPServer:
    server = MCPServer("test")

    @server.tool(name="zabbix_get_problem")
    def get_problem(eventid: str) -> dict:
        return {**ENVELOPE, "data": {**ENVELOPE["data"], "eventid": eventid}}

    @server.tool(name="zabbix_get_host")
    def get_host(hostid: str) -> dict:
        return {
            "ok": False,
            "collected_at": "2026-10-15T01:00:00Z",
            "reason": "NOT_FOUND",
            "message": "없음",
        }

    if extra_tool:

        @server.tool(name=extra_tool)
        def write_tool(hostid: str) -> dict:  # 불리면 안 된다
            raise AssertionError("쓰기 도구가 호출됨")

    return server


class InProcessClient(McpToolClient):
    """HTTP 대신 같은 프로세스의 MCPServer 에 붙는다. 검사·봉투 처리는 실제 코드 그대로."""

    def __init__(self, server: MCPServer):
        super().__init__("http://unused/mcp")
        self._server = server

    def _http(self):
        return contextlib.nullcontext(None)

    def _client(self, http) -> Client:
        return Client(self._server)


def test_call_returns_structured_envelope():
    client = InProcessClient(_server())
    result = client.call("zabbix_get_problem", {"eventid": "42"})
    assert result["ok"] is True
    assert result["data"]["eventid"] == "42"
    assert result["data"]["items"][0]["itemid"] == "9"


def test_failure_envelope_passes_through():
    result = InProcessClient(_server()).call("zabbix_get_host", {"hostid": "0"})
    assert result == {
        "ok": False,
        "collected_at": "2026-10-15T01:00:00Z",
        "reason": "NOT_FOUND",
        "message": "없음",
    }


def test_allowed_but_unregistered_tool_is_failure_envelope():
    result = InProcessClient(_server()).call("zabbix_list_items", {"hostid": "1"})
    assert result["ok"] is False and result["reason"] == "ZABBIX_ERROR"


def test_tool_outside_allow_list_rejected_before_connect():
    with pytest.raises(ForbiddenToolError):
        McpToolClient("http://127.0.0.1:9/mcp").call("zabbix_delete_host", {})


@pytest.mark.safety_regression
def test_write_tool_on_server_blocks_every_call(safety_results):
    """SAFE-03: 서버가 쓰기 도구를 내놓으면 허용된 도구도 부르지 않는다."""
    client = InProcessClient(_server(extra_tool="zabbix_delete_host"))
    blocked = False
    try:
        client.call("zabbix_get_problem", {"eventid": "1"})
    except ForbiddenToolError:
        blocked = True
    safety_results["dangerous"].append(blocked)
    assert blocked


@pytest.mark.safety_regression
def test_startup_refuses_mcp_with_write_tool(settings, packs_dir, safety_results):
    """SAFE-03: 실 MCP 클라이언트 경로로도 쓰기 도구가 보이면 기동 실패."""
    client = InProcessClient(_server(extra_tool="zabbix_delete_host"))
    refused = False
    try:
        with TestClient(
            create_app(settings, packs_dir, tool_client=client, start_worker=False)
        ):
            pass
    except ForbiddenToolError:
        refused = True
    safety_results["dangerous"].append(refused)
    assert refused


def test_startup_continues_when_mcp_unreachable(tmp_path, packs_dir):
    s = Settings.from_env(
        {
            "SHARED_DB_PATH": str(tmp_path / "s.db"),
            "DOMAIN_PACK": "test",
            "MCP_ZABBIX_URL": "http://127.0.0.1:9/mcp",
        }
    )
    with TestClient(create_app(s, packs_dir, start_worker=False)) as client:
        assert client.get("/healthz").json()["mcp"] == {"zabbix": "down"}


def test_startup_check_unreachable_does_not_raise():
    asyncio.run(startup_check(McpToolClient("http://127.0.0.1:9/mcp")))


def test_make_tool_client_by_url():
    assert isinstance(make_tool_client(Settings.from_env({})), UnavailableToolClient)
    made = make_tool_client(Settings.from_env({"MCP_ZABBIX_URL": "http://m:8200/mcp"}))
    assert isinstance(made, McpToolClient)


def test_envelope_of_text_and_unknown_shapes():
    text = SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(text='{"ok": true, "data": [], "collected_at": "x"}')],
    )
    assert envelope_of(text)["ok"] is True
    junk = SimpleNamespace(structured_content={"a": 1}, content=[], is_error=False)
    assert envelope_of(junk)["ok"] is False
    err = SimpleNamespace(structured_content=None, content=[], is_error=True)
    assert envelope_of(err)["reason"] == "ZABBIX_ERROR"
