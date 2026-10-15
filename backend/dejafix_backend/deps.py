"""공통 의존성: DB 연결, 현재 사용자, 역할 검사.

역할 등급: viewer < operator < admin. require_role("operator") 는 operator 이상을 통과시킨다.
"""

from collections.abc import Callable, Iterator
from typing import Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from dejafix_backend.config import Settings, get_settings
from dejafix_backend.db import Db, open_db
from dejafix_backend.errors import ApiError
from dejafix_backend.security import decode_token

ROLE_RANK = {"viewer": 1, "operator": 2, "admin": 3}

_bearer = HTTPBearer(auto_error=False)


def get_db(settings: Settings = Depends(get_settings)) -> Iterator[Db]:
    db = open_db(settings)
    try:
        yield db
    finally:
        db.close()


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Db = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if creds is None:
        raise ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다")
    try:
        claims = decode_token(settings.jwt_secret, creds.credentials)
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, ValueError):
        raise ApiError(401, "UNAUTHORIZED", "토큰이 없거나 만료되었습니다") from None
    row = db.conn.execute(
        "SELECT id, username, display_name, email, role FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        raise ApiError(401, "UNAUTHORIZED", "존재하지 않는 사용자입니다")
    return dict(row)


def require_role(minimum: str) -> Callable[..., dict[str, Any]]:
    def checker(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if ROLE_RANK.get(user["role"], 0) < ROLE_RANK[minimum]:
            raise ApiError(403, "FORBIDDEN", "권한이 없습니다")
        return user

    return checker
