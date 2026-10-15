"""MCP 도구 접점 (FR-AG-010, SAFE-03·05).

- Agent가 부를 수 있는 도구는 contracts/mcp-tools.md 의 조회 도구 12개뿐이다.
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
    }
)


class ForbiddenToolError(RuntimeError):
    """MCP 도구 목록에 허용 목록 밖 도구가 있음 → 기동 실패 (SAFE-03)."""


def check_tool_list(names: list[str]) -> None:
    extra = sorted(set(names) - ALLOWED_TOOLS)
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
