"""시드 계정 admin(admin) · oncall(operator).

비밀번호는 .env 의 DEMO_ADMIN_PASSWORD·DEMO_ONCALL_PASSWORD 에서만 읽는다.
이미 있는 계정은 건드리지 않는다. 비밀번호가 비어 있으면 그 계정은 만들지 않는다.
"""

import logging

from dejafix_backend.config import Settings
from dejafix_backend.db import open_db
from dejafix_backend.security import hash_password
from dejafix_backend.timeutil import utc_now_iso

log = logging.getLogger("dejafix.backend")


def ensure_seed_users(settings: Settings) -> int:
    """없는 시드 계정만 만든다. 만든 개수를 반환."""
    seeds = [
        ("admin", settings.demo_admin_password, "관리자", "admin@example.com", "admin"),
        (
            "oncall",
            settings.demo_oncall_password,
            "당직자",
            "oncall@example.com",
            "operator",
        ),
    ]
    db = open_db(settings)
    created = 0
    try:
        for username, password, display_name, email, role in seeds:
            if not password:
                log.warning(
                    "%s 시드를 건너뜁니다 (비밀번호 환경 변수가 비어 있음)", username
                )
                continue
            cur = db.conn.execute(
                "INSERT OR IGNORE INTO users"
                " (username, password_hash, display_name, email, role, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    username,
                    hash_password(password),
                    display_name,
                    email,
                    role,
                    utc_now_iso(),
                ),
            )
            created += cur.rowcount
        db.conn.commit()
    finally:
        db.close()
    return created
