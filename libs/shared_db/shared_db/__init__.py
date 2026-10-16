"""공유 DB 스키마 적용·연결 공용 모듈 (T35, FR-DATA-003·004, DR-016·019).

스키마 원본은 contracts/db-schema.sql 하나다. 이 모듈은 그 파일을
`-- @db shared` / `-- @db backend` 구역으로 나눠 해당 DB에만 적용한다.

- Agent·Scheduler: apply_schema(conn, "shared")
- Backend: apply_schema(conn, "backend")  (shared.db 는 읽기 전용 ATTACH)
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

__all__ = [
    "SECTIONS",
    "SchemaError",
    "find_contract",
    "load_sections",
    "connect",
    "apply_schema",
    "open_db",
    "load_dev_seed",
]

SECTIONS = ("shared", "backend")
_MARKER = re.compile(r"^-- @db (\w+)\s*$", re.MULTILINE)
_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA foreign_keys=ON",
)


class SchemaError(RuntimeError):
    """스키마 파일을 찾지 못했거나 구역이 잘못됐을 때."""


def find_contract(name: str = "db-schema.sql", start: Path | None = None) -> Path:
    """이 파일에서 위로 올라가며 contracts/<name> 을 찾는다.

    저장소에서 실행하든, 루트 빌드 컨텍스트로 만든 컨테이너에서 실행하든
    같은 상대 위치(contracts/)를 쓴다.
    """
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "contracts" / name
        if candidate.is_file():
            return candidate
    raise SchemaError(f"contracts/{name} 을 찾을 수 없음 (시작: {here})")


def load_sections(path: Path) -> dict[str, str]:
    """`-- @db <이름>` 표시로 SQL을 구역별로 나눈다."""
    text = Path(path).read_text(encoding="utf-8")
    parts = _MARKER.split(text)
    sections = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    if not sections:
        raise SchemaError(f"{path}: '-- @db' 구역 표시가 없음")
    return sections


def connect(db_path: str | Path, *, uri: bool = False) -> sqlite3.Connection:
    """PRAGMA(WAL·busy_timeout·foreign_keys)를 켠 연결을 연다.

    uri=True 이면 db_path 를 'file:...' URI로 해석한다. Backend 처럼
    다른 DB를 '?mode=ro' 로 ATTACH 하려면 uri=True 로 열어야 한다.
    """
    target = str(db_path)
    if not uri and target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, uri=uri)
    for pragma in _PRAGMAS:
        conn.execute(pragma)
    return conn


def apply_schema(
    conn: sqlite3.Connection, section: str, schema_path: Path | None = None
) -> None:
    """해당 구역의 DDL만 실행한다. 모든 문장이 IF NOT EXISTS 라 여러 번 실행해도 된다."""
    if section not in SECTIONS:
        raise SchemaError(f"알 수 없는 구역: {section!r} (가능: {SECTIONS})")
    sections = load_sections(schema_path or find_contract())
    if section not in sections:
        raise SchemaError(f"스키마에 '{section}' 구역이 없음")
    conn.executescript(sections[section])
    conn.commit()


def open_db(
    db_path: str | Path, section: str, schema_path: Path | None = None
) -> sqlite3.Connection:
    """연결을 열고 해당 구역 스키마를 적용해 돌려준다 (서비스 기동 시 한 번)."""
    conn = connect(db_path)
    apply_schema(conn, section, schema_path)
    return conn


def load_dev_seed(conn: sqlite3.Connection, section: str) -> None:
    """개발용 시드(fixtures/seed_dev.sql)의 해당 구역을 넣는다. 데모·운영 DB 금지."""
    seed = Path(__file__).resolve().parent.parent / "fixtures" / "seed_dev.sql"
    sections = load_sections(seed)
    if section not in sections:
        raise SchemaError(f"시드에 '{section}' 구역이 없음")
    conn.executescript(sections[section])
    conn.commit()
