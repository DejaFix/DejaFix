"""AI Agent FastAPI 앱 (:8100, 내부 전용).

기동 순서: 설정 → 도메인 팩 로드(실패하면 기동 중단) → MCP 도구 목록 검사(허용 밖이면 중단)
→ shared.db 스키마 멱등 적용 → 분석 워커(10초 주기) 시작. 채팅은 다음 PR에서 붙는다.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from shared_db import open_db

from . import worker
from .config import Settings
from .packs import load_pack
from .tools import ToolClient, UnavailableToolClient, check_tool_list

log = logging.getLogger("dejafix.agent")


def _mcp_health_url(mcp_url: str) -> str | None:
    """MCP_ZABBIX_URL(http://host:8200/mcp) → http://host:8200/healthz"""
    if not mcp_url:
        return None
    base = mcp_url.rstrip("/")
    if base.endswith("/mcp"):
        base = base[: -len("/mcp")]
    return base + "/healthz"


async def mcp_status(settings: Settings) -> str:
    url = _mcp_health_url(settings.mcp_zabbix_url)
    if url is None:
        return "down"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url)
        return "ok" if resp.status_code == 200 else "down"
    except httpx.HTTPError:
        return "down"


def create_app(
    settings: Settings | None = None,
    packs_dir: Path | None = None,
    tool_client: ToolClient | None = None,
    start_worker: bool = True,
) -> FastAPI:
    """packs_dir·tool_client·start_worker 는 테스트에서만 바꾼다."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        pack = load_pack(settings.domain_pack, packs_dir)  # PackError → 기동 실패
        app.state.pack = pack
        # 실 MCP 클라이언트는 mcp-zabbix 서버(T42)가 생기면 붙인다. 그 전엔 모든 조회가 TOOL_ERROR.
        client = tool_client or UnavailableToolClient()
        check_tool_list(client.list_tools())  # 허용 밖 도구 → 기동 실패 (SAFE-03)
        app.state.tool_client = client
        open_db(settings.shared_db_path, "shared").close()

        def db_factory():
            return open_db(settings.shared_db_path, "shared")

        task = None
        if start_worker:
            task = asyncio.create_task(worker.loop(db_factory, settings, pack, client))
        log.info(
            "agent started: pack=%s llm_mode=%s",
            settings.domain_pack,
            settings.llm_mode,
        )
        try:
            yield
        finally:
            if task:
                task.cancel()

    app = FastAPI(title="DejaFix Agent", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "ok": True,
            "model": settings.model_label,
            "mcp": {"zabbix": await mcp_status(settings)},
        }

    return app


app = create_app()
