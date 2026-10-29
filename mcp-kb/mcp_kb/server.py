"""RAG 지식 검색 MCP 서버 (FR-RAG-006, contracts/mcp-tools.md 6장).

- streamable HTTP `/mcp`, `GET /healthz`. tools/list 에는 `kb_search_knowledge` 하나만(SAFE-03).
- knowledge.db 는 요청마다 읽기 전용으로 연다(색인기가 갱신해도 바로 반영, 쓰기 불가).
- 실패는 공통 봉투 `{ok:false, reason:"KB_ERROR"}`. 예외 원문·경로·키를 넣지 않는다.
- 선택 `INTERNAL_TOKEN` 이 있으면 `/mcp` 요청에 Bearer 토큰을 요구한다.
"""

from __future__ import annotations

import hmac
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dejafix_kb.config import KbSettings
from dejafix_kb.embed import EmbedSettings, Embedder, HttpEmbedder
from dejafix_kb.search import search
from dejafix_kb.store import open_kb_readonly

TOOL_NAME = "kb_search_knowledge"
KB_ERROR = "KB_ERROR"
MAX_K = 5
SOURCE_TYPES = {"incident_report", "runbook", "pack_action", "resolution_note"}


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "collected_at": now_iso(),
        "reason": KB_ERROR,
        "message": message,
    }


class KbSearcher:
    def __init__(self, db_path: Path, embedder: Embedder | None):
        self.db_path = db_path
        self.embedder = embedder

    def _open(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError
        return open_kb_readonly(self.db_path)

    def search(
        self,
        query: str,
        k: int = MAX_K,
        source_types: list[str] | None = None,
        host_name: str | None = None,
        exclude_source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not query or not query.strip():
            return _fail("query 가 비어 있음")
        k = max(1, min(int(k or MAX_K), MAX_K))
        types = [t for t in (source_types or []) if t in SOURCE_TYPES] or None
        try:
            conn = self._open()
        except (FileNotFoundError, sqlite3.Error):
            return _fail("지식 저장소를 열 수 없음 (색인 전)")
        try:
            hits, info = search(
                conn,
                query,
                k,
                self.embedder,
                types,
                host_name or None,
                exclude_source_ids or None,
            )
        except sqlite3.Error:
            return _fail("지식 저장소 조회 실패")
        finally:
            conn.close()
        return {
            "ok": True,
            "collected_at": now_iso(),
            "data": {"mode": info["mode"], "hits": [h.to_dict() for h in hits]},
            "truncated": False,
        }

    def health(self) -> dict[str, Any]:
        try:
            conn = self._open()
        except (FileNotFoundError, sqlite3.Error):
            return {"ok": True, "kb": "down", "documents": 0, "chunks": 0}
        try:
            docs = conn.execute("SELECT COUNT(*) FROM kb_documents").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0]
        except sqlite3.Error:
            return {"ok": True, "kb": "down", "documents": 0, "chunks": 0}
        finally:
            conn.close()
        return {
            "ok": True,
            "kb": "ok" if chunks else "empty",
            "documents": docs,
            "chunks": chunks,
        }


def build_server(searcher: KbSearcher) -> MCPServer:
    server = MCPServer("mcp-kb")

    @server.tool(
        name=TOOL_NAME,
        description=(
            "과거 장애 리포트·런북·팩 동작 설명·해결 메모에서 질문과 비슷한 지식을 찾는다(최대 5건). "
            "결과는 근거(chunk_id)일 뿐 티어를 정하지 않는다. 결과가 없으면 관련 지식 없음."
        ),
    )
    def kb_search_knowledge(
        query: str,
        k: int = MAX_K,
        source_types: list[str] | None = None,
        host_name: str | None = None,
        exclude_source_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return searcher.search(query, k, source_types, host_name, exclude_source_ids)

    @server.custom_route("/healthz", methods=["GET"])
    async def healthz(_request: Request) -> Response:
        return JSONResponse(searcher.health())

    return server


class _InternalTokenGuard:
    """INTERNAL_TOKEN 이 있으면 /healthz 외 요청에 Bearer 토큰을 요구한다(mcp-zabbix 와 같은 방식)."""

    def __init__(self, app, token: str):
        self._app = app
        self._token = token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/healthz":
            headers = dict(scope.get("headers") or [])
            if not hmac.compare_digest(
                headers.get(b"authorization", b""), b"Bearer " + self._token
            ):
                await JSONResponse(
                    {"ok": False, "reason": "UNAUTHORIZED"}, status_code=401
                )(scope, receive, send)
                return
        await self._app(scope, receive, send)


def make_searcher(env: dict[str, str] | None = None) -> KbSearcher:
    settings = KbSettings.from_env(env)
    es = EmbedSettings.from_env(env)
    return KbSearcher(
        settings.path(settings.kb_db_path), HttpEmbedder(es) if es.enabled else None
    )


def build_app(searcher: KbSearcher | None = None):
    app = build_server(searcher or make_searcher()).streamable_http_app()
    token = os.environ.get("INTERNAL_TOKEN", "").strip()
    return _InternalTokenGuard(app, token) if token else app
