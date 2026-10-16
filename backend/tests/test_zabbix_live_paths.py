"""실연동 준비(T63 코드 경로) — ZABBIX_MOCK=false 에서 API 4·5·6번이 **진짜 zabbix_ro + HTTP** 를 거쳐 동작하는지.

대역 클라이언트가 아니라 JSON-RPC 를 흉내 내는 작은 HTTP 서버를 `ZABBIX_URL` 로 쓴다. 실서버 확인(토큰을 `.env` 에 넣은 뒤)은 사람이 한다.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

TOKEN = "test-token-not-real-0123456789"
CLOCK = "1792027200"  # 2026-10-15T01:20:00Z


class Zabbix:
    """JSON-RPC 서버 상태: 메서드별 결과·오류, 받은 요청 기록."""

    results: dict = {}
    mode = "ok"  # ok | rpc_error | http500 | slow
    requests: list = []


@pytest.fixture
def zabbix_server():
    Zabbix.results = {
        "apiinfo.version": "7.0.31",
        "host.get": [
            {"hostid": "10001", "status": "0", "active_available": "1"},
            {"hostid": "10002", "status": "0", "active_available": "1"},
            {"hostid": "10003", "status": "0", "active_available": "0"},
        ],
        "problem.get": [
            {
                "eventid": "30001",
                "objectid": "20001",
                "name": "High CPU utilization (over 90% for 1m)",
                "severity": "4",
                "clock": CLOCK,
                "r_eventid": "0",
                "tags": [{"tag": "scope", "value": "performance"}],
            }
        ],
        "trigger.get": [
            {
                "triggerid": "20001",
                "hosts": [
                    {"hostid": "10002", "host": "demo-host", "name": "demo-host"}
                ],
            }
        ],
    }
    Zabbix.mode, Zabbix.requests = "ok", []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
            )
            Zabbix.requests.append(
                {"method": body["method"], "auth": self.headers.get("Authorization")}
            )
            if Zabbix.mode == "slow":
                time.sleep(4)
            if Zabbix.mode == "http500":
                self.send_response(500)
                self.end_headers()
                return
            if Zabbix.mode == "rpc_error":
                payload = {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": "Invalid params.",
                        "data": "No permissions to referred object.",
                    },
                    "id": body["id"],
                }
            else:
                payload = {
                    "jsonrpc": "2.0",
                    "result": Zabbix.results[body["method"]],
                    "id": body["id"],
                }
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.url = f"http://127.0.0.1:{server.server_address[1]}/api_jsonrpc.php"
    yield server
    server.shutdown()
    server.server_close()


def live_client(make_client, helpers, url, token=TOKEN, **env):
    client = make_client(
        ZABBIX_MOCK="false", ZABBIX_URL=url, ZABBIX_API_TOKEN=token, **env
    )
    return client, helpers.login(client, "oncall", helpers.oncall_password)


def fetch(client, headers):
    health = client.get("/api/health", headers=headers)
    summary = client.get("/api/dashboard/summary", headers=headers)
    problems = client.get("/api/problems", headers=headers)
    return health, summary, problems


# ---------------------------------------------------------------- 진짜 zabbix_ro + HTTP 로 정상 동작


def test_api_4_5_6_work_end_to_end_through_zabbix_ro_and_http(
    make_client, helpers, zabbix_server
):
    client, headers = live_client(make_client, helpers, zabbix_server.url)
    health, summary, problems = fetch(client, headers)

    assert health.json()["data"]["zabbix"] == "ok"
    hosts = summary.json()["data"]["hosts"]
    assert (
        hosts["total"]["value"],
        hosts["ok"]["value"],
        hosts["unknown"]["value"],
    ) == (3, 1, 1)
    # 호스트 10002 는 활성 문제(30001)가 있어 정상에서 빠지고, 10003 은 가용성을 알 수 없다
    assert problems.status_code == 200
    item = problems.json()["data"][0]
    assert item["eventid"] == "30001" and item["host"] == {
        "id": "10002",
        "name": "demo-host",
    }
    assert (
        item["severity"] == {"level": 4, "label": "High"}
        and item["clock"] == "2026-10-15T01:20:00Z"
    )


@pytest.mark.safety_regression
def test_only_read_methods_are_sent_and_the_token_is_a_bearer_header_never_in_responses(
    make_client, helpers, zabbix_server
):
    client, headers = live_client(make_client, helpers, zabbix_server.url)
    responses = fetch(client, headers)
    methods = {r["method"] for r in Zabbix.requests}
    assert methods == {
        "apiinfo.version",
        "host.get",
        "problem.get",
        "trigger.get",
    }  # 읽기 메서드뿐 (SAFE-02)
    # 인증은 Authorization: Bearer 헤더로만, apiinfo.version 은 인증 없이
    for request in Zabbix.requests:
        if request["method"] == "apiinfo.version":
            assert request["auth"] is None
        else:
            assert request["auth"] == f"Bearer {TOKEN}"
    for response in responses:
        assert TOKEN not in response.text  # 토큰은 어떤 응답에도 없다


# ---------------------------------------------------------------- 설정이 비어 있을 때


@pytest.mark.safety_regression
@pytest.mark.parametrize(
    "url,token",
    [("", ""), ("", TOKEN), ("http://127.0.0.1:9/api_jsonrpc.php", "")],
    ids=["둘 다 없음", "URL 없음", "토큰 없음"],
)
def test_missing_url_or_token_degrades_every_api_without_a_crash_and_sends_nothing(
    make_client, helpers, zabbix_server, url, token
):
    client, headers = live_client(make_client, helpers, url, token)
    health, summary, problems = fetch(client, headers)
    assert health.status_code == 200 and health.json()["data"]["zabbix"] == "down"
    assert summary.status_code == 200
    hosts = summary.json()["data"]["hosts"]
    assert all(
        hosts[k]["unknown"] and hosts[k]["unknown_reason"] == "TOOL_ERROR"
        for k in hosts
    )
    assert (
        problems.status_code == 503
        and problems.json()["error"]["code"] == "ZABBIX_UNAVAILABLE"
    )
    assert Zabbix.requests == []  # 어디로도 요청이 나가지 않았다


def test_connection_refused_degrades_every_api(make_client, helpers):
    client, headers = live_client(
        make_client, helpers, "http://127.0.0.1:9/api_jsonrpc.php"
    )
    health, summary, problems = fetch(client, headers)
    assert health.json()["data"]["zabbix"] == "down"
    assert summary.json()["data"]["hosts"]["total"]["unknown_reason"] == "TOOL_ERROR"
    assert problems.status_code == 503


# ---------------------------------------------------------------- Zabbix 가 이상하게 답할 때


@pytest.mark.parametrize("mode", ["rpc_error", "http500"])
def test_zabbix_errors_degrade_every_api_and_never_leak_details(
    make_client, helpers, zabbix_server, mode
):
    Zabbix.mode = mode
    client, headers = live_client(make_client, helpers, zabbix_server.url)
    responses = fetch(client, headers)
    health, summary, problems = responses
    assert health.json()["data"]["zabbix"] == "down"
    assert summary.json()["data"]["hosts"]["ok"]["unknown_reason"] == "TOOL_ERROR"
    assert problems.status_code == 503
    for response in responses:  # JSON-RPC 오류 내용·토큰이 응답에 새지 않는다
        assert "No permissions" not in response.text and TOKEN not in response.text


def test_a_slow_zabbix_does_not_hold_the_screen_up(make_client, helpers, zabbix_server):
    Zabbix.mode = "slow"
    client, headers = live_client(
        make_client, helpers, zabbix_server.url, ZABBIX_TIMEOUT_SEC="0.4"
    )
    started = time.monotonic()
    health, summary, problems = fetch(client, headers)
    elapsed = time.monotonic() - started
    assert health.json()["data"]["zabbix"] == "down"
    assert summary.json()["data"]["hosts"]["total"]["unknown"] is True
    assert problems.status_code == 503
    # Zabbix 가 4초씩 걸려도 기다리지 않는다 (health 3초 한도 + 나머지 두 API 0.4초 한도씩)
    assert elapsed < 5.5


def test_zabbix_recovers_without_restarting_the_backend(
    make_client, helpers, zabbix_server
):
    """Zabbix 가 잠깐 끊겼다 돌아오면 백엔드를 다시 켜지 않아도 짧은 실패 캐시(2초)가 지난 뒤 정상으로 돌아온다."""
    Zabbix.mode = "rpc_error"
    client, headers = live_client(
        make_client, helpers, zabbix_server.url, ZABBIX_FAILURE_TTL_SEC="0.3"
    )
    assert client.get("/api/problems", headers=headers).status_code == 503
    Zabbix.mode = "ok"
    time.sleep(0.5)  # 실패 캐시 시간이 지난다
    assert client.get("/api/problems", headers=headers).status_code == 200
