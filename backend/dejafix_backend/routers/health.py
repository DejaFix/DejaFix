"""#4 GET /api/health  (T31)

구성요소가 죽어도 200 으로 상태만 알려 준다. 값은 "ok" | "down", shared_db 만 "waiting" 이 추가된다.
zabbix 는 libs/zabbix_ro(T30) 연결 전까지 ZABBIX_MOCK 값으로만 판단한다. (TODO: T30 에서 apiinfo.version 로 교체)
"""

import asyncio
import sqlite3
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from dejafix_backend.config import Settings, get_settings
from dejafix_backend.db import open_db
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.timeutil import utc_now_iso

router = APIRouter(tags=["health"])


def _db_status(settings: Settings) -> dict[str, Any]:
    result: dict[str, Any] = {
        "backend_db": "down",
        "shared_db": "waiting",
        "scheduler_last_ok": None,
    }
    try:
        db = open_db(settings)
    except sqlite3.Error:
        return result
    try:
        db.conn.execute("SELECT 1").fetchone()
        result["backend_db"] = "ok"
        if db.shared_ok:
            result["shared_db"] = "ok"
            try:
                row = db.conn.execute(
                    "SELECT last_ok_at FROM shared.scheduler_jobs"
                    " WHERE job = 'poll_problems'"
                ).fetchone()
                result["scheduler_last_ok"] = row["last_ok_at"] if row else None
            except sqlite3.Error:
                result["scheduler_last_ok"] = None  # 아직 기록이 없으면 null
    except sqlite3.Error:
        result["backend_db"] = "down"
    finally:
        db.close()
    return result


def _origin(url: str) -> str:
    """http://mcp-zabbix:8200/mcp -> http://mcp-zabbix:8200"""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


async def _probe(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        return "down"
    return "ok" if response.status_code == 200 else "down"


@router.get("/health")
async def health(
    _: dict = Depends(require_role("viewer")),
    settings: Settings = Depends(get_settings),
):
    async with httpx.AsyncClient(timeout=1.0) as client:
        agent, mcp, db_part = await asyncio.gather(
            _probe(client, f"{_origin(settings.agent_url)}/healthz"),
            _probe(client, f"{_origin(settings.mcp_zabbix_url)}/healthz"),
            run_in_threadpool(_db_status, settings),
        )
    data = {
        "zabbix": "ok" if settings.zabbix_mock else "down",
        "agent": agent,
        "mcp_zabbix": mcp,
        **db_part,
    }
    return ok(data, checked_at=utc_now_iso())
