"""공통 응답 봉투와 커서 페이지네이션 헬퍼.

성공: {"data": ..., "meta": {...}}   실패: {"error": {"code", "message"}} (errors.py)
커서는 클라이언트가 해석하지 않는 불투명 문자열이다 (base64url JSON).
"""

import base64
import json
from typing import Any


def ok(data: Any, **meta: Any) -> dict[str, Any]:
    return {"data": data, "meta": meta}


def encode_cursor(**fields: Any) -> str:
    raw = json.dumps(fields, separators=(",", ":"), ensure_ascii=False).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """형식이 잘못된 커서는 ValueError."""
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        fields = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(fields, dict):
        raise ValueError("invalid cursor")
    return fields
