"""mcp-zabbix 실 MCP 클라이언트 (T47, FR-AG-010, SAFE-03·05).

- streamable HTTP(`MCP_ZABBIX_URL`)로 붙는다. `INTERNAL_TOKEN` 이 있으면 Bearer 로 보낸다.
- 세션을 열 때마다 도구 목록을 먼저 검사한다. 허용 목록 밖 도구가 하나라도 있으면
  ForbiddenToolError 를 올리고 아무 도구도 부르지 않는다(SAFE-03).
- 결과는 contracts/mcp-tools.md 공통 봉투. MCP 응답의 `structured_content` 를 그대로 쓰고,
  없으면 text 본문을 JSON 으로 읽는다. 봉투가 아니면 실패 봉투로 바꾼다(지어내지 않음).
- 동기 인터페이스(ToolClient)다. 워커는 스레드(asyncio.to_thread)에서 부르고,
  기동 검사처럼 이벤트 루프 안에서는 `alist_tools()` 를 쓴다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from .tools import (
    ALLOWED_TOOLS,
    ZABBIX_SERVER_TOOLS,
    ForbiddenToolError,
    check_tool_list,
)

log = logging.getLogger("dejafix.agent.mcp")

READ_TIMEOUT_SEC = 30.0


def _fail(message: str) -> dict[str, Any]:
    return {"ok": False, "reason": "ZABBIX_ERROR", "message": message}


def envelope_of(result: Any) -> dict[str, Any]:
    """MCP CallToolResult → 공통 봉투 dict. 모양을 모르면 실패 봉투."""
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict) and "ok" in structured:
        return structured
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "ok" in parsed:
            return parsed
    if getattr(result, "is_error", False):
        return _fail("MCP 도구 호출 오류")
    return _fail("MCP 응답 형식을 알 수 없음")


class McpToolClient:
    def __init__(
        self,
        url: str,
        token: str = "",
        read_timeout: float = READ_TIMEOUT_SEC,
        allowed: frozenset[str] = ZABBIX_SERVER_TOOLS,
    ):
        self.allowed = allowed  # 이 서버가 내놓아도 되는 도구 집합 (SAFE-03, 서버별)
        self._url = url
        self._token = token
        self._read_timeout = read_timeout

    def _client(self, http) -> Client:
        return Client(
            streamable_http_client(self._url, http_client=http),
            read_timeout_seconds=self._read_timeout,
        )

    def _http(self):
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        return create_mcp_http_client(headers=headers)

    @staticmethod
    async def _names(client: Client) -> list[str]:
        listed = await client.list_tools()
        return [t.name for t in listed.tools]

    # 검사 예외는 세션(async with) 밖에서 올린다. 안에서 올리면 MCP 클라이언트의
    # 태스크 그룹이 ExceptionGroup 으로 감싸서 ForbiddenToolError 로 잡히지 않는다.
    async def alist_tools(self) -> list[str]:
        async with self._http() as http, self._client(http) as client:
            names = await self._names(client)
        check_tool_list(
            names, self.allowed
        )  # 허용 밖 도구 → ForbiddenToolError (SAFE-03)
        return names

    async def acall(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool not in self.allowed:
            raise ForbiddenToolError(tool)
        result = None
        async with self._http() as http, self._client(http) as client:
            names = await self._names(client)
            # 허용 밖 도구가 하나라도 있으면 허용된 도구도 부르지 않는다
            if not set(names) - self.allowed and tool in names:
                result = await client.call_tool(tool, args)
        check_tool_list(names, self.allowed)
        if result is None:
            return _fail(f"MCP 서버에 {tool} 도구가 없음")
        return envelope_of(result)

    def list_tools(self) -> list[str]:
        return asyncio.run(self.alist_tools())

    def call(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self.acall(tool, args))


async def startup_check(client: Any, allowed: frozenset[str] = ALLOWED_TOOLS) -> None:
    """기동 시 도구 목록 검사 (SAFE-03).

    허용 밖 도구가 있으면 예외를 그대로 올려 기동을 멈춘다. MCP 서버에 아직 닿지 않으면
    (compose 기동 순서 등) 경고만 남긴다 — 이후 호출마다 세션을 열 때 다시 검사한다.
    """
    try:
        if isinstance(client, McpToolClient):
            names = await client.alist_tools()
        else:
            names = await asyncio.to_thread(client.list_tools)
            check_tool_list(names, allowed)
    except ForbiddenToolError:
        raise
    except Exception as exc:  # 연결 실패는 기동을 막지 않는다
        log.warning("MCP 도구 목록 확인 실패(나중에 다시 검사): %s", type(exc).__name__)
        return
    log.info("MCP 도구 %d개 확인", len(names))
