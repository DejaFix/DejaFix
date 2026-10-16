import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ZABBIX_TOKEN = "test-token-not-real-0123456789"


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


@pytest.fixture
def fake_zabbix():
    """JSON-RPC 요청을 기록하고 정해진 응답을 주는 작은 Zabbix 흉내. 동작은 .mode 로 바꾼다."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            server.requests.append(
                {"headers": dict(self.headers), "body": json.loads(body)}
            )
            if server.mode == "slow":
                time.sleep(5)
            if server.mode == "http500":
                self.send_response(500)
                self.end_headers()
                return
            if server.mode == "rpc_error":
                payload = {"jsonrpc": "2.0", "error": {"code": -32500, "message": "x"}}
            elif server.mode == "empty_version":
                payload = {"jsonrpc": "2.0", "result": "", "id": 1}
            else:
                payload = {"jsonrpc": "2.0", "result": "7.0.31", "id": 1}
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.mode = "ok"
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}/api_jsonrpc.php"
    yield server
    server.shutdown()
    server.server_close()


def _zabbix_health(make_client, helpers, **env):
    client = make_client(ZABBIX_MOCK="false", ZABBIX_API_TOKEN=ZABBIX_TOKEN, **env)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    response = client.get("/api/health", headers=headers)
    assert response.status_code == 200
    assert ZABBIX_TOKEN not in response.text  # 토큰은 응답에 나오지 않는다
    return response.json()["data"]["zabbix"]


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


# ---------------------------------------------------------------- zabbix: apiinfo.version


def test_health_zabbix_ok_when_apiinfo_version_answers(
    make_client, helpers, fake_zabbix
):
    assert _zabbix_health(make_client, helpers, ZABBIX_URL=fake_zabbix.url) == "ok"
    sent = fake_zabbix.requests[0]
    assert sent["body"]["method"] == "apiinfo.version"
    assert "Authorization" not in sent["headers"]  # apiinfo.version 은 인증 없이


@pytest.mark.parametrize("mode", ["http500", "rpc_error", "empty_version"])
def test_health_zabbix_down_when_zabbix_misbehaves(
    make_client, helpers, fake_zabbix, mode
):
    fake_zabbix.mode = mode
    assert _zabbix_health(make_client, helpers, ZABBIX_URL=fake_zabbix.url) == "down"


def test_health_zabbix_down_when_connection_refused(make_client, helpers):
    url = "http://127.0.0.1:9/api_jsonrpc.php"
    assert _zabbix_health(make_client, helpers, ZABBIX_URL=url) == "down"


def test_health_zabbix_down_when_url_missing_without_calling_anything(
    make_client, helpers
):
    assert _zabbix_health(make_client, helpers) == "down"


def test_health_does_not_wait_for_a_slow_zabbix(make_client, helpers, fake_zabbix):
    """Zabbix 가 5초 걸려도 health 는 3초 안에(+여유) 응답하고 zabbix 만 down."""
    fake_zabbix.mode = "slow"
    started = time.monotonic()
    status = _zabbix_health(make_client, helpers, ZABBIX_URL=fake_zabbix.url)
    elapsed = time.monotonic() - started
    assert status == "down"
    assert elapsed < 4.5


def test_health_zabbix_mock_mode_makes_no_network_call(
    make_client, helpers, fake_zabbix
):
    client = make_client(ZABBIX_MOCK="true", ZABBIX_URL=fake_zabbix.url)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    data = client.get("/api/health", headers=headers).json()["data"]
    assert data["zabbix"] == "ok"
    assert fake_zabbix.requests == []


def test_health_zabbix_calls_are_cached_briefly_and_shared(
    make_client, helpers, fake_zabbix
):
    """화면 여러 곳이 15초마다 불러도 Zabbix 에는 가볍게: 5초 안의 health 호출은 한 번만 Zabbix 로 간다."""
    client = make_client(
        ZABBIX_MOCK="false", ZABBIX_API_TOKEN=ZABBIX_TOKEN, ZABBIX_URL=fake_zabbix.url
    )
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    for _ in range(4):
        data = client.get("/api/health", headers=headers).json()["data"]
        assert data["zabbix"] == "ok"
    assert len(fake_zabbix.requests) == 1
