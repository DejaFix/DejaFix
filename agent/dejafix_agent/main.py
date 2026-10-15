"""AI Agent FastAPI 앱 (:8100, 내부 전용).

기동 순서: 설정 → 도메인 팩 로드(실패하면 기동 중단) → shared.db 스키마 멱등 적용.
분석 워커·채팅은 다음 PR에서 붙는다.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from shared_db import open_db

from .config import Settings
from .packs import load_pack

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
    settings: Settings | None = None, packs_dir: Path | None = None
) -> FastAPI:
    """packs_dir 는 테스트에서 시험 팩 폴더를 가리킬 때만 넘긴다."""
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.pack = load_pack(
            settings.domain_pack, packs_dir
        )  # PackError → 기동 실패
        conn = open_db(settings.shared_db_path, "shared")
        conn.close()
        log.info(
            "agent started: pack=%s llm_mode=%s",
            settings.domain_pack,
            settings.llm_mode,
        )
        yield

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
