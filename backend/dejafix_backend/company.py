"""회사 (결정 019, contracts/api.md 1장 "회사").

- `DEFAULT_COMPANY_ID` 가 없으면 회사 나누기가 꺼져 있다: `X-AX-Company` 를 무시하고 지금처럼, 응답 머리도 없음.
- 켜져 있으면 요청 회사는:
  - `COMPANY_HEADER_ACCOUNTS` 에 적은 계정(AXcellent 프록시 viewer·admin): `X-AX-Company`, 없으면 기본 회사
  - 그 밖의 계정(사람이 직접 로그인): `users.company_id`(비면·칸이 없으면 기본 회사). 머리가 다르면 403
  - 머리 형식이 틀리면 422 VALIDATION_ERROR
- 요청 회사는 `CURRENT`(contextvar)와 `request.state.company` 에 둔다. 응답에는 `X-DejaFix-Company`.
- shared.db 의 incidents 에 company_id 칸이 아직 없으면(Scheduler 019 이관 전) 회사로 거를 수 없으니
  #10·#11 등은 503 SHARED_DB_UNAVAILABLE — 회사 없이 섞어 읽지 않는다.
"""

from __future__ import annotations

import sqlite3
from contextvars import ContextVar
from typing import Any

import zabbix_ro

from dejafix_backend.config import Settings
from dejafix_backend.errors import ApiError

HEADER = "X-AX-Company"
ECHO = "X-DejaFix-Company"

# 요청 회사. None = 회사 나누기 꺼짐
CURRENT: ContextVar[str | None] = ContextVar("dejafix_company", default=None)


def enabled(settings: Settings) -> bool:
    return bool(settings.default_company_id.strip())


def default(settings: Settings) -> str:
    return settings.default_company_id.strip()


def header_accounts(settings: Settings) -> set[str]:
    return {a.strip() for a in settings.company_header_accounts.split(",") if a.strip()}


def _user_company(conn: sqlite3.Connection, user_id: int) -> str | None:
    """users.company_id (칸이 없거나 비면 None = 기본 회사)."""
    cols = {row[1] for row in conn.execute("PRAGMA main.table_info(users)")}
    if "company_id" not in cols:
        return None
    row = conn.execute(
        "SELECT company_id FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    value = row[0] if row else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve(
    settings: Settings,
    conn: sqlite3.Connection,
    user: dict[str, Any],
    header: str | None,
) -> str | None:
    """요청 회사. 꺼져 있으면 None."""
    if not enabled(settings):
        return None
    raw = (header or "").strip()
    if raw and not zabbix_ro.COMPANY_ID_RE.match(raw):
        raise ApiError(422, "VALIDATION_ERROR", f"{HEADER} 형식이 올바르지 않습니다")
    if user.get("username") in header_accounts(settings):
        return raw or default(settings)
    own = _user_company(conn, int(user["id"])) or default(settings)
    if raw and raw != own:
        raise ApiError(403, "FORBIDDEN", "권한이 없습니다")
    return own


def current() -> str | None:
    return CURRENT.get()


def is_default(settings: Settings, company: str | None = None) -> bool:
    company = current() if company is None else company
    return company is None or company == default(settings)


def incidents_scoped(conn: sqlite3.Connection) -> bool:
    """shared.incidents 에 company_id 칸이 있는가 (Scheduler 019 이관 뒤)."""
    try:
        cols = {row[1] for row in conn.execute("PRAGMA shared.table_info(incidents)")}
    except sqlite3.Error:
        return False
    return "company_id" in cols


def incident_filter(conn: sqlite3.Connection, alias: str = "i") -> tuple[str, tuple]:
    """(SQL 조건, 인자). 꺼져 있으면 ("", ()). 켜져 있는데 이관 전이면 503."""
    company = current()
    if company is None:
        return "", ()
    if not incidents_scoped(conn):
        raise ApiError(
            503, "SHARED_DB_UNAVAILABLE", "공유 DB가 아직 회사별로 준비되지 않았습니다"
        )
    return f"{alias}.company_id = ?", (company,)
