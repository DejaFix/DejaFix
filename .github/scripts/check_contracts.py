"""contracts/ 형식 검증 (CI safety job).

- *.schema.json: JSON Schema(선언한 $schema 버전)로서 유효한지
- db-schema.sql: 모든 CREATE 문이 IF NOT EXISTS 이고(루트 CLAUDE.md DB 규칙), 빈 SQLite에 두 번 적용해도 오류가 없는지
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

from jsonschema.validators import validator_for

ROOT = Path(__file__).resolve().parents[2] / "contracts"
errors: list[str] = []

for path in sorted(ROOT.glob("*.schema.json")):
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
        validator_for(schema).check_schema(schema)
        print(f"ok  {path.name}")
    except Exception as exc:  # 파싱·스키마 오류 모두 실패로 보고
        errors.append(f"{path.name}: {type(exc).__name__}: {exc}")

sql_path = ROOT / "db-schema.sql"
sql = sql_path.read_text(encoding="utf-8")
missing = [
    m.group(0).strip()
    for m in re.finditer(r"^\s*CREATE\s+(?!.*IF\s+NOT\s+EXISTS).*$", sql, re.I | re.M)
]
if missing:
    errors.append(
        f"db-schema.sql: IF NOT EXISTS 없는 CREATE {len(missing)}건: {missing[:3]}"
    )
try:
    conn = sqlite3.connect(":memory:")
    conn.executescript(sql)
    conn.executescript(sql)  # 재적용(기동마다 실행) 시에도 오류가 없어야 한다
    tables = conn.execute(
        "select count(*) from sqlite_master where type='table'"
    ).fetchone()[0]
    print(f"ok  db-schema.sql (테이블 {tables}개, 2회 적용)")
except sqlite3.Error as exc:
    errors.append(f"db-schema.sql: {exc}")

if errors:
    for e in errors:
        print(f"::error::{e}")
    sys.exit(1)
