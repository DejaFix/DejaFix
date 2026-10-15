import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@pytest.fixture
def fake_service():
    """GET /healthz 에 200 을 주는 작은 서버 (Agent·MCP 흉내)."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            ok = self.path == "/healthz"
            self.send_response(200 if ok else 404)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_healthz_is_public(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_waiting_before_shared_db_exists(client, oncall):
    """Agent 기동 전: 500 이 아니라 200 + shared_db:"waiting"."""
    response = client.get("/api/health", headers=oncall)
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == {
        "zabbix": "ok",  # ZABBIX_MOCK=true
        "agent": "down",
        "mcp_zabbix": "down",
        "shared_db": "waiting",
        "backend_db": "ok",
        "scheduler_last_ok": None,
    }
    assert body["meta"]["checked_at"].endswith("Z")


def test_health_retries_every_request_when_shared_db_appears(
    env, client, oncall, helpers
):
    assert (
        client.get("/api/health", headers=oncall).json()["data"]["shared_db"]
        == "waiting"
    )
    helpers.build_shared_db(env.shared)
    data = client.get("/api/health", headers=oncall).json()["data"]
    assert data["shared_db"] == "ok"


def test_health_reports_scheduler_last_ok(make_client, helpers):
    client = make_client(seeded=True)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    data = client.get("/api/health", headers=headers).json()["data"]
    assert data["shared_db"] == "ok"
    assert data["scheduler_last_ok"] == "2026-10-15T01:25:20Z"


def test_health_zabbix_down_when_not_mock(make_client, helpers):
    client = make_client(ZABBIX_MOCK="false")
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    assert client.get("/api/health", headers=headers).json()["data"]["zabbix"] == "down"


def test_health_agent_and_mcp_ok(make_client, helpers, fake_service):
    client = make_client(AGENT_URL=fake_service, MCP_ZABBIX_URL=f"{fake_service}/mcp")
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    data = client.get("/api/health", headers=headers).json()["data"]
    assert data["agent"] == "ok"
    assert (
        data["mcp_zabbix"] == "ok"
    )  # URL 의 /mcp 경로가 아니라 서버 주소의 /healthz 를 본다


def test_health_is_available_to_viewer(client, viewer):
    assert client.get("/api/health", headers=viewer).status_code == 200
