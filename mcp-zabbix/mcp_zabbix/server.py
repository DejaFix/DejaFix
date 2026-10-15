"""mcp-zabbix 서버 — streamable HTTP `:8200/mcp`, `GET /healthz` (FR-MCP-001, FR-INF-002).

- 등록 도구는 필수 5개뿐(contracts/mcp-tools.md 4장). planned·쓰기 도구는 등록하지 않는다(FR-MCP-009, SAFE-03).
- 결과는 structuredContent 와 content[0].text 에 같은 봉투 JSON (계약 2장).
- Zabbix 가 죽어도 서버는 살아 있고 도구가 ZABBIX_ERROR 를 돌려준다.
"""

from __future__ import annotations

import os
from typing import Any

import zabbix_ro
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import tools

REQUIRED_TOOLS = (
    "zabbix_list_problems",
    "zabbix_get_problem",
    "zabbix_get_host",
    "zabbix_list_items",
    "zabbix_get_history",
)


def create_server(client: Any | None = None, mock: bool | None = None) -> FastMCP:
    """client·mock 은 테스트에서만 넘긴다. 기본은 환경 변수(ZABBIX_*)로 만든 zabbix_ro 클라이언트."""
    zbx = client if client is not None else zabbix_ro.from_env()
    is_mock = bool(getattr(zbx, "mock", False)) if mock is None else mock

    server = FastMCP(
        "mcp-zabbix",
        instructions="DejaFix 읽기 전용 Zabbix 조회 도구. 쓰기·설정 변경 도구는 없다.",
        stateless_http=True,
        json_response=True,
        # compose 내부 이름(mcp-zabbix)으로 부르므로 Host 검사를 끈다. 외부 포트는 공개하지 않는다(SAFE-14).
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )

    @server.tool(structured_output=True)
    def zabbix_list_problems(
        severity_min: int = 0,
        hostid: str | None = None,
        since: str | int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """열린 장애 목록(최신순, 최대 100건). 호스트 정보 포함. since 는 UTC ISO8601 또는 유닉스 초."""
        return tools.list_problems(zbx, severity_min, hostid, since, limit)

    @server.tool(structured_output=True)
    def zabbix_get_problem(eventid: str) -> dict[str, Any]:
        """장애 1건 상세: 트리거 조건식과 관련 지표 항목(items) 포함. 없으면 NOT_FOUND."""
        return tools.get_problem(zbx, eventid)

    @server.tool(structured_output=True)
    def zabbix_get_host(hostid: str) -> dict[str, Any]:
        """호스트 1건: 가용성, 그룹, 유지보수 중 여부. 주소(ip·dns)는 주지 않는다."""
        return tools.get_host(zbx, hostid)

    @server.tool(structured_output=True)
    def zabbix_list_items(hostid: str, key_search: str | None = None) -> dict[str, Any]:
        """호스트의 지표 항목과 최신값(최대 100건). 항목마다 stale(오래됨) 판정."""
        return tools.list_items(zbx, hostid, key_search)

    @server.tool(structured_output=True)
    def zabbix_get_history(
        itemid: str,
        time_from: str | int,
        time_till: str | int | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """지표 이력(최대 500점, 시간순). 24시간을 넘는 범위는 요약값(trend)."""
        return tools.get_history(zbx, itemid, time_from, time_till, limit)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(_: Request) -> JSONResponse:
        if is_mock:
            state = "mock"
        else:
            try:
                zbx.call("apiinfo.version", {})
                state = "ok"
            except Exception:  # noqa: BLE001
                state = "down"
        return JSONResponse({"ok": True, "zabbix": state})

    return server


def main() -> None:
    import uvicorn

    host = os.environ.get("MCP_ZABBIX_BIND") or "127.0.0.1"
    port = int(os.environ.get("MCP_ZABBIX_PORT") or 8200)
    uvicorn.run(create_server().streamable_http_app(), host=host, port=port)
