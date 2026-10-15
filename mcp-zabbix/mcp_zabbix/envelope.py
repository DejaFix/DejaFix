"""공통 봉투·시각·오래된 값 판정 (contracts/mcp-tools.md 2장, IF-INT-MCP-001, FR-MCP-007·008).

- 성공 {ok:true, collected_at, data, truncated}, 실패 {ok:false, collected_at, reason, message}
- reason 은 NO_PERMISSION | NOT_FOUND | ZABBIX_ERROR 셋뿐. 예외·스택·Zabbix 원문은 넘기지 않는다.
- stale = (now - lastclock) > max(delay초 × 3, 600초), lastclock 이 "0"·없음이면 stale.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Any

from zabbix_ro import MethodNotAllowed, ZabbixError, ZabbixRoError

MAX_LIST = 100  # NFR-PERF-007
MAX_POINTS = 500
MIN_STALE_SEC = 600

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_DELAY = re.compile(r"^\s*(\d+)\s*([smhdw]?)\s*$")


def now_iso(ts: float | None = None) -> str:
    dt = datetime.fromtimestamp(time.time() if ts is None else ts, UTC)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ok(data: Any, truncated: bool = False) -> dict[str, Any]:
    return {"ok": True, "collected_at": now_iso(), "data": data, "truncated": truncated}


def fail(reason: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "collected_at": now_iso(),
        "reason": reason,
        "message": message,
    }


def from_error(exc: Exception) -> dict[str, Any]:
    """zabbix_ro 예외 → 실패 봉투. 원문 오류는 한 줄 요약만 남긴다."""
    if isinstance(exc, MethodNotAllowed):
        return fail("ZABBIX_ERROR", "허용되지 않은 조회")
    if isinstance(exc, ZabbixError):
        text = f"{exc} {exc.data or ''}".lower()
        if "no permissions" in text or "permission" in text:
            return fail("NO_PERMISSION", "조회 권한 없음")
        return fail("ZABBIX_ERROR", "Zabbix 조회 실패")
    if isinstance(exc, ZabbixRoError):
        return fail("ZABBIX_ERROR", "Zabbix 조회 실패")
    return fail("ZABBIX_ERROR", "MCP 내부 오류")


def parse_time(value: Any, default: int | None = None) -> int | None:
    """UTC ISO8601 문자열 또는 유닉스 초(정수·문자열) → 유닉스 초."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise ValueError("시각 형식이 아님")
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def delay_seconds(delay: Any) -> int | None:
    """'30s'·'1m'·'1h'·'60' → 초. 사용자 매크로·복합 간격이면 None."""
    m = _DELAY.match(str(delay or ""))
    if not m:
        return None
    return int(m.group(1)) * _UNITS[m.group(2) or "s"]


def is_stale(lastclock: Any, delay: Any, now: float | None = None) -> bool:
    try:
        last = int(str(lastclock))
    except (TypeError, ValueError):
        return True
    if last <= 0:
        return True
    sec = delay_seconds(delay) or 0
    limit = max(sec * 3, MIN_STALE_SEC)
    return ((time.time() if now is None else now) - last) > limit
