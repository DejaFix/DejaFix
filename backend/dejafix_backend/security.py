"""비밀번호 해시(bcrypt)와 JWT(HS256)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

ALGORITHM = "HS256"

# 존재하지 않는 사용자에게도 같은 시간이 걸리도록 쓰는 더미 해시
DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


def create_token(
    secret: str, user_id: int, role: str, expire_min: int
) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=expire_min)
    payload = {"sub": str(user_id), "role": role, "exp": expires}
    return jwt.encode(payload, secret, algorithm=ALGORITHM), expires


def decode_token(secret: str, token: str) -> dict[str, Any]:
    """만료·위조 토큰은 jwt.PyJWTError 를 올린다."""
    return jwt.decode(
        token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
    )
