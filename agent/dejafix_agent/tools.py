"""MCP 도구 접점 (FR-AG-010, SAFE-03·05).

- Agent가 부를 수 있는 도구는 contracts/mcp-tools.md 4장의 조회 도구 13개뿐이다(mcp-kb 의 kb_search_knowledge 포함, v0.2).
  이름 패턴이 아니라 명시 집합으로 검사한다(zabbix_api_version 처럼 패턴에 안 맞는 조회 도구가 있음).
- MCP 서버가 허용 목록 밖 도구를 하나라도 내놓으면 Agent는 기동하지 않는다.
- 셸·SSH·임의 HTTP 도구는 없다. 외부 조회는 이 인터페이스로만 한다.
"""

from __future__ import annotations

from typing import Any, Protocol

ALLOWED_TOOLS = frozenset(
    {
        "zabbix_list_problems",
        "zabbix_get_problem",
        "zabbix_list_hosts",
        "zabbix_get_host",
        "zabbix_list_items",
        "zabbix_get_history",
        "zabbix_get_trends",
        "zabbix_list_triggers",
        "zabbix_get_event_history",
        "zabbix_list_host_groups",
        "zabbix_get_alert_settings",
        "zabbix_api_version",
        "kb_search_knowledge",  # mcp-kb (contracts/mcp-tools.md 6장, [이후])
    }
)
KB_TOOL = "kb_search_knowledge"
# 서버별 기대 집합 (contracts/mcp-tools.md 6장: mcp-kb 에는 kb_search_knowledge 하나만, mcp-zabbix 에는 kb_ 없음)
ZABBIX_SERVER_TOOLS = ALLOWED_TOOLS - {KB_TOOL}
KB_SERVER_TOOLS = frozenset({KB_TOOL})


class ForbiddenToolError(RuntimeError):
    """MCP 도구 목록에 허용 목록 밖 도구가 있음 → 기동 실패 (SAFE-03)."""


def check_tool_list(names: list[str], allowed: frozenset[str] = ALLOWED_TOOLS) -> None:
    extra = sorted(set(names) - allowed)
    if extra:
        raise ForbiddenToolError(f"허용 목록 밖 MCP 도구: {extra}")


class ToolClient(Protocol):
    """MCP 도구 호출. 결과는 공통 봉투 {ok, collected_at, data, truncated?} 또는 {ok:false, reason}."""

    def list_tools(self) -> list[str]: ...

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]: ...


class UnavailableToolClient:
    """MCP_ZABBIX_URL 이 없거나 서버가 아직 없을 때. 모든 호출이 TOOL_ERROR 로 기록된다."""

    def list_tools(self) -> list[str]:
        return []

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool not in ALLOWED_TOOLS:
            raise ForbiddenToolError(tool)
        return {
            "ok": False,
            "reason": "ZABBIX_ERROR",
            "message": "MCP 서버에 연결되지 않음",
        }


class RoutedToolClient:
    """mcp-zabbix 와 mcp-kb 두 서버를 하나의 ToolClient 처럼 쓴다. kb_ 도구만 mcp-kb 로 보낸다.

    MCP_KB_URL 이 있을 때만 만든다(없으면 기존 단일 클라이언트 그대로).
    """

    kb_enabled = True

    def __init__(self, main: ToolClient, kb: ToolClient):
        self.main = main
        self.kb = kb

    def list_tools(self) -> list[str]:
        return self.main.list_tools() + self.kb.list_tools()

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool not in ALLOWED_TOOLS:
            raise ForbiddenToolError(tool)
        return (self.kb if tool.startswith("kb_") else self.main).call(tool, args)
