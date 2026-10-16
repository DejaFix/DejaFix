"""개발 시드: libs/shared_db/README.md "시드 넣기"와 같은 동작. 저장소 루트 기준으로 경로를 푼다.

    uv run --no-project --python 3.12 python -I scripts/seed_dev.py [출력 폴더, 기본 data]

구역(-- @db shared / backend)을 해당 DB에만 적용한다. 이미 있는 DB에 다시 실행해도 행이 늘지 않는다.
"""

import pathlib
import re
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sections(path: pathlib.Path) -> dict[str, str]:
    parts = re.split(r"^-- @db (\w+)\s*$", path.read_text(encoding="utf-8"), flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"
if not out.is_absolute():
    out = ROOT / out
out.mkdir(parents=True, exist_ok=True)
schema = sections(ROOT / "contracts" / "db-schema.sql")
seed = sections(ROOT / "libs" / "shared_db" / "fixtures" / "seed_dev.sql")
for db in ("shared", "backend"):
    conn = sqlite3.connect(out / f"{db}.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(schema[db])
    conn.executescript(seed[db])
    conn.commit()
    conn.close()
print(f"ok {out}")
