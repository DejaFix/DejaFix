"""테스트 공통 준비.

- 스키마·시드는 팀 원본(contracts/db-schema.sql, libs/shared_db/fixtures/seed_dev.sql)을 그대로 쓴다.
- 구역(-- @db shared / backend)별로 해당 DB 에만 적용한다.
- 모든 DB 는 tmp_path 의 임시 파일이고 ZABBIX_MOCK=true, Agent·MCP 는 닫힌 포트를 가리킨다.
"""

import sqlite3
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dejafix_backend.config import get_settings
from dejafix_backend.db import split_zones
from dejafix_backend.main import create_app
from dejafix_backend.security import hash_password

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "contracts" / "db-schema.sql"
SEED = REPO / "libs" / "shared_db" / "fixtures" / "seed_dev.sql"
INCIDENT_SCHEMA = REPO / "contracts" / "incident.schema.json"

ADMIN_PASSWORD = "admin-pass-test"
ONCALL_PASSWORD = "oncall-pass-test"
VIEWER_PASSWORD = "viewer-pass-test"


def _zone(path: Path, name: str) -> str:
    return split_zones(path.read_text(encoding="utf-8"))[name]


def build_shared_db(path: Path) -> None:
    """shared 구역 스키마 + 시드 장애 6건을 shared.db 에 만든다."""
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_zone(SCHEMA, "shared"))
        conn.executescript(_zone(SEED, "shared"))
        conn.commit()
    finally:
        conn.close()


def seed_backend_db(path: Path) -> None:
    """앱이 만든 backend.db 에 시드 메일 기록(backend 구역)을 넣는다."""
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_zone(SEED, "backend"))
        conn.commit()
    finally:
        conn.close()


def add_user(path: Path, username: str, role: str, password: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, display_name, email, role,"
            " created_at) VALUES (?, ?, ?, ?, ?, '2026-10-15T00:00:00Z')",
            (
                username,
                hash_password(password),
                username,
                f"{username}@example.com",
                role,
            ),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def env(tmp_path, monkeypatch):
    values = {
        "JWT_SECRET": "test-secret-test-secret-test-secret-32b",
        "DEMO_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "DEMO_ONCALL_PASSWORD": ONCALL_PASSWORD,
        "BACKEND_DB_PATH": str(tmp_path / "backend.db"),
        "SHARED_DB_PATH": str(tmp_path / "shared.db"),
        "DB_SCHEMA_PATH": str(SCHEMA),
        "ZABBIX_MOCK": "true",
        # 저장소 루트의 로컬 .env 에 실서버 값이 있어도 테스트가 실제 Zabbix 를 부르지 않게 비워 둔다
        "ZABBIX_URL": "",
        "ZABBIX_API_TOKEN": "",
        "ZABBIX_VERIFY_TLS": "",
        "AGENT_URL": "http://127.0.0.1:9",
        "MCP_ZABBIX_URL": "http://127.0.0.1:9/mcp",
        "INTERNAL_TOKEN": "",
        "CHAT_STREAMING": "true",
        "CHAT_FIRST_EVENT_TIMEOUT_SEC": "3",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield SimpleNamespace(
        shared=tmp_path / "shared.db", backend=tmp_path / "backend.db"
    )
    get_settings.cache_clear()


@pytest.fixture
def make_client(env, monkeypatch):
    """환경 변수를 바꿔 가며 앱을 새로 띄우는 공장. seeded=True 면 시드 shared.db 를 만든다."""
    stack = ExitStack()

    def make(seeded: bool = False, **extra: str) -> TestClient:
        for key, value in extra.items():
            monkeypatch.setenv(key.upper(), str(value))
        get_settings.cache_clear()
        if seeded:
            build_shared_db(env.shared)
        client = stack.enter_context(TestClient(create_app()))
        if seeded:
            seed_backend_db(env.backend)
        return client

    yield make
    stack.close()


@pytest.fixture
def client(make_client):
    """shared.db 가 아직 없는 상태(Agent·Scheduler 기동 전)."""
    return make_client()


@pytest.fixture
def seeded_client(make_client):
    """시드 장애 6건이 들어 있는 shared.db 와 시드 메일 기록."""
    return make_client(seeded=True)


def login(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['data']['token']}"}


@pytest.fixture
def helpers():
    """테스트가 쓰는 도구 모음. (--import-mode=importlib 에서는 conftest 를 import 할 수 없다)"""
    return SimpleNamespace(
        login=login,
        build_shared_db=build_shared_db,
        add_user=add_user,
        schema=SCHEMA,
        incident_schema=INCIDENT_SCHEMA,
        admin_password=ADMIN_PASSWORD,
        oncall_password=ONCALL_PASSWORD,
        viewer_password=VIEWER_PASSWORD,
    )


@pytest.fixture
def oncall(client):
    return login(client, "oncall", ONCALL_PASSWORD)


@pytest.fixture
def viewer(env, client):
    add_user(env.backend, "viewer", "viewer", VIEWER_PASSWORD)
    return login(client, "viewer", VIEWER_PASSWORD)
