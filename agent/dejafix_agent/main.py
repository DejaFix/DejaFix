"""AI Agent FastAPI 앱 (:8100, 내부 전용).

기동 순서: 설정 → 도메인 팩 로드(실패하면 기동 중단) → MCP 도구 목록 검사(허용 밖이면 중단)
→ shared.db 스키마 멱등 적용 → 분석 워커(10초 주기) 시작. 채팅은 POST /v1/chat (SSE).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from shared_db import open_db

from . import chat, worker
from .config import Settings
from .mcp_client import McpToolClient, startup_check
from .packs import load_pack
from .tools import ToolClient, UnavailableToolClient

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


def make_tool_client(settings: Settings) -> ToolClient:
    """MCP_ZABBIX_URL 이 있으면 실 MCP 클라이언트, 없으면 모든 조회가 TOOL_ERROR."""
    if not settings.mcp_zabbix_url:
        return UnavailableToolClient()
    return McpToolClient(settings.mcp_zabbix_url, settings.internal_token)


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
        client = tool_client or make_tool_client(settings)
        await startup_check(client)  # 허용 밖 도구 → 기동 실패 (SAFE-03)
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

    @app.post("/v1/chat")
    async def chat_endpoint(request: Request):
        """contracts/agent-api.md 1-2. meta 를 먼저 보내고 답을 만든 뒤 final 로 닫는다."""
        try:
            body = await request.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        raw_user = request.headers.get("X-User-Id")
        user_id = int(raw_user) if raw_user and raw_user.isdigit() else None
        caller = str(body.get("caller") or "backend")
        db_path = settings.shared_db_path
        try:
            started = await asyncio.to_thread(
                chat.start, db_path, body, user_id, caller, settings.model_label
            )
        except chat.ChatError as exc:
            return JSONResponse(
                {"error": {"code": exc.code, "message": exc.message}},
                status_code=exc.status,
            )
        message = str(body.get("message")).strip()
        pack = request.app.state.pack

        async def events():
            yield chat.sse(
                "meta",
                {
                    "conversation_id": started.conversation_id,
                    "run_id": started.run_id,
                    "message_id": started.message_id,
                },
            )
            try:
                ans = await asyncio.to_thread(
                    chat.answer, settings, pack, message, started.context
                )
                if ans.from_llm:
                    for i in range(0, len(ans.content), 40):
                        yield chat.sse("token", {"text": ans.content[i : i + 40]})
                msg_id = await asyncio.to_thread(chat.finish, db_path, started, ans)
                yield chat.sse(
                    "final",
                    {
                        "message_id": msg_id,
                        "content": ans.content,
                        "evidence_ids": ans.evidence_ids,
                        "unknowns": ans.unknowns,
                    },
                )
            except Exception as exc:
                log.exception("chat failed: run=%s", started.run_id)
                partial = chat.Answer("", [], [], False)
                await asyncio.to_thread(
                    chat.finish, db_path, started, partial, "INTERNAL_ERROR"
                )
                yield chat.sse(
                    "error",
                    {"code": "INTERNAL_ERROR", "message": type(exc).__name__},
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "ok": True,
            "model": settings.model_label,
            "mcp": {"zabbix": await mcp_status(settings)},
        }

    return app


app = create_app()
