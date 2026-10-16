"""SQLite 연결.

- backend.db : Backend 전용 (users, mail_logs). 여기에만 쓴다.
- shared.db  : Agent·Scheduler 가 쓰는 공유 DB. `ATTACH 'file:...?mode=ro' AS shared` 로
  읽기 전용으로만 붙인다 — 쓰기는 연결 수준에서 거부된다 (FR-BE-014).
  파일이 아직 없으면 attach 를 건너뛰고 shared_ok=False ("waiting") 로 둔다. 요청마다 재시도한다.
- backend.db 를 uri=True 로 열어야 'file:...?mode=ro' 형식의 ATTACH 가 동작한다.
- 스키마 원본은 contracts/db-schema.sql. "-- @db backend" 구역만 backend.db 에 적용한다.
  구역을 섞어 적용하면 backend.db 안에 빈 incidents 같은 그림자 테이블이 생겨 ATTACH 한
  shared.incidents 대신 잘못 읽힌다.
- 상대 DB 경로는 저장소 루트 기준으로 푼다(실행 위치 무관). 절대 경로인데 부모 폴더가 없으면
  새 빈 DB 를 조용히 만들지 않고 경로를 남기며 실패한다 (예: Windows 에서 '/data/...' -> C:/data).
"""

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from dejafix_backend.config import ROOT, Settings

log = logging.getLogger("dejafix.backend")

_ZONE = re.compile(r"^--\s*@db\s+(\w+)\s*$", re.MULTILINE)

_REQUIRED_USER_COLUMNS = {
    "id",
    "username",
    "password_hash",
    "display_name",
    "email",
    "role",
    "created_at",
    "last_login_at",
}


@dataclass
class Db:
    conn: sqlite3.Connection
    shared_ok: bool

    def close(self) -> None:
        self.conn.close()


def db_file(path: str) -> Path:
    """DB 경로를 절대 경로로 푼다. 상대 경로는 cwd 가 아니라 저장소 루트 기준."""
    p = Path(path)
    # Windows 의 '/data/x' 는 드라이브가 없어 is_absolute() 가 False 지만 루트 기준 경로다.
    return (p if p.anchor else ROOT / p).resolve()


def _backend_db_file(path: str) -> Path:
    """backend.db 경로. 루트 아래 상대 경로만 부모 폴더를 만들고, 그 밖은 없으면 실패한다."""
    file = db_file(path)
    if not file.parent.exists():
        if Path(path).anchor:
            log.error(
                "backend.db 폴더가 없습니다: %s (BACKEND_DB_PATH=%s)", file.parent, path
            )
            raise RuntimeError(
                f"backend.db 폴더가 없습니다: {file.parent} (BACKEND_DB_PATH={path}). "
                "로컬은 data/backend.db 처럼 상대 경로를 쓰세요."
            )
        file.parent.mkdir(parents=True, exist_ok=True)
    return file


def _file_uri(file: Path, mode: str) -> str:
    return f"{file.as_uri()}?mode={mode}"


def _pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")


def open_db(settings: Settings) -> Db:
    """backend.db 를 열고 shared.db 를 읽기 전용으로 붙인다 (없으면 shared_ok=False)."""
    backend_file = _backend_db_file(settings.backend_db_path)
    conn = sqlite3.connect(
        _file_uri(backend_file, "rwc"), uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    _pragmas(conn)
    shared_ok = False
    shared_file = db_file(settings.shared_db_path)
    if shared_file.exists():
        try:
            conn.execute("ATTACH DATABASE ? AS shared", (_file_uri(shared_file, "ro"),))
            shared_ok = True
        except sqlite3.OperationalError as exc:
            log.warning("shared.db attach 실패, waiting 으로 처리: %s", exc)
    return Db(conn=conn, shared_ok=shared_ok)


def split_zones(sql: str) -> dict[str, str]:
    """'-- @db <이름>' 구역별로 SQL 을 나눈다. 구역 표시 앞의 머리말은 버린다."""
    parts = _ZONE.split(sql)  # [머리말, 이름1, 본문1, 이름2, 본문2, ...]
    return dict(zip(parts[1::2], parts[2::2]))


def schema_path(settings: Settings) -> Path:
    if settings.db_schema_path:
        return Path(settings.db_schema_path)
    # backend/dejafix_backend/db.py -> 저장소 루트
    return Path(__file__).resolve().parents[2] / "contracts" / "db-schema.sql"


def init_backend_db(settings: Settings) -> None:
    """backend.db 에 팀 스키마의 backend 구역을 멱등 적용한다 (전 문장 IF NOT EXISTS)."""
    path = schema_path(settings)
    if not path.exists():
        raise RuntimeError(f"스키마 파일을 찾을 수 없습니다: {path} (DB_SCHEMA_PATH)")
    zone = split_zones(path.read_text(encoding="utf-8")).get("backend")
    if not zone:
        raise RuntimeError(f"{path} 에 '-- @db backend' 구역이 없습니다")

    conn = sqlite3.connect(
        _file_uri(_backend_db_file(settings.backend_db_path), "rwc"), uri=True
    )
    try:
        _pragmas(conn)
        conn.executescript(zone)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    finally:
        conn.close()

    missing = _REQUIRED_USER_COLUMNS - columns
    if missing:
        raise RuntimeError(f"users 테이블에 필요한 컬럼이 없습니다: {sorted(missing)}")
