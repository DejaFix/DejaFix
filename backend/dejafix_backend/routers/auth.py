"""#1 POST /api/auth/login, #3 GET /api/auth/me  (T29)"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dejafix_backend.config import Settings, get_settings
from dejafix_backend.db import Db
from dejafix_backend.deps import current_user, get_db
from dejafix_backend.envelope import ok
from dejafix_backend.errors import ApiError
from dejafix_backend.security import DUMMY_HASH, create_token, verify_password
from dejafix_backend.timeutil import to_iso, utc_now_iso

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(
    body: LoginRequest,
    db: Db = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    row = db.conn.execute(
        "SELECT id, username, password_hash, display_name, role"
        " FROM users WHERE username = ?",
        (body.username,),
    ).fetchone()
    # 사용자 유무와 상관없이 해시 검증을 한 번 수행해 응답 시간으로 계정 존재를 알 수 없게 한다
    valid = verify_password(body.password, row["password_hash"] if row else DUMMY_HASH)
    if row is None or not valid:
        raise ApiError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 틀렸습니다")

    db.conn.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?", (utc_now_iso(), row["id"])
    )
    db.conn.commit()
    token, expires = create_token(
        settings.jwt_secret, row["id"], row["role"], settings.jwt_expire_min
    )
    user = {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "display_name": row["display_name"],
    }
    return ok({"token": token, "user": user}, expires_at=to_iso(expires))


@router.get("/me")
def me(user: dict[str, Any] = Depends(current_user)):
    return ok(user)
