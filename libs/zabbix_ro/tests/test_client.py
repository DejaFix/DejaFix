"""zabbix_ro 클라이언트 — SAFE-02(허용 목록 밖은 요청 전에 거부), Bearer 인증, 오류 변환, 목 모드."""

import json

import httpx
import pytest

import zabbix_ro
from zabbix_ro import (
    ALLOWED_METHODS,
    MethodNotAllowed,
    ZabbixError,
    ZabbixRoError,
    from_env,
)

URL = "http://zabbix.test/api_jsonrpc.php"
TOKEN = "test-token-not-real"


class Recorder:
    """보낸 요청을 기록하고 정해진 응답을 돌려주는 가짜 전송 계층."""

    def __init__(self, handler=None):
        self.requests: list[httpx.Request] = []
        self.handler = handler or (
            lambda req: httpx.Response(
                200, json={"jsonrpc": "2.0", "result": [], "id": 1}
            )
        )

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self.handler(request)

        return httpx.MockTransport(handle)


def real_client(rec: Recorder, **env):
    base = {"ZABBIX_URL": URL, "ZABBIX_API_TOKEN": TOKEN, "ZABBIX_MOCK": "false"}
    base.update(env)
    return from_env(base, transport=rec.transport())


# ---------------------------------------------------------------- SAFE-02


@pytest.mark.safety_regression
@pytest.mark.parametrize(
    "method",
    [
        "host.update",
        "item.create",
        "user.login",
        "problem.delete",
        "trigger.delete",
        "host.massupdate",
        "script.execute",
        "configuration.import",
        "event.acknowledge",
        "",
        "PROBLEM.GET",
    ],
)
def test_safe02_disallowed_method_raises_before_any_request(method):
    rec = Recorder()
    client = real_client(rec)
    with pytest.raises(MethodNotAllowed):
        client.call(method, {"hostid": "1"})
    assert rec.requests == []  # 네트워크로 나가지 않았다


@pytest.mark.safety_regression
def test_safe02_disallowed_method_is_blocked_in_mock_mode_too():
    client = from_env({"ZABBIX_MOCK": "true"})
    with pytest.raises(MethodNotAllowed):
        client.call("host.update", {})


@pytest.mark.safety_regression
def test_allowlist_is_exactly_the_13_read_methods():
    assert ALLOWED_METHODS == {
        "apiinfo.version",
        "problem.get",
        "event.get",
        "trigger.get",
        "host.get",
        "hostgroup.get",
        "hostinterface.get",
        "item.get",
        "history.get",
        "trend.get",
        "maintenance.get",
        "action.get",
        "alert.get",
    }
    assert all(m.endswith(".get") or m == "apiinfo.version" for m in ALLOWED_METHODS)


def test_allowed_method_passes():
    rec = Recorder()
    assert real_client(rec).call("problem.get", {"recent": True}) == []
    assert len(rec.requests) == 1


# ---------------------------------------------------------------- 인증·요청 형식


def test_bearer_token_header_and_no_auth_field_in_body():
    rec = Recorder()
    real_client(rec).call("problem.get", {"output": "extend"})
    req = rec.requests[0]
    body = json.loads(req.content)
    assert req.method == "POST"
    assert str(req.url) == URL
    assert req.headers["authorization"] == f"Bearer {TOKEN}"
    assert req.headers["content-type"] == "application/json-rpc"
    assert "auth" not in body
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "problem.get"
    assert body["params"] == {"output": "extend"}


def test_apiinfo_version_is_sent_without_auth():
    rec = Recorder(
        lambda r: httpx.Response(
            200, json={"jsonrpc": "2.0", "result": "7.0.31", "id": 1}
        )
    )
    assert real_client(rec).call("apiinfo.version") == "7.0.31"
    assert "authorization" not in rec.requests[0].headers


def test_request_ids_increase():
    rec = Recorder()
    client = real_client(rec)
    client.call("host.get", {})
    client.call("host.get", {})
    ids = [json.loads(r.content)["id"] for r in rec.requests]
    assert ids == [1, 2]


@pytest.mark.parametrize(
    "value,expected",
    [(None, True), ("", True), ("true", True), ("false", False), ("0", False)],
)
def test_verify_tls_flag(value, expected):
    env = {"ZABBIX_URL": URL, "ZABBIX_API_TOKEN": TOKEN}
    if value is not None:
        env["ZABBIX_VERIFY_TLS"] = value
    client = from_env(env, transport=Recorder().transport())
    assert client.verify_tls is expected


# ---------------------------------------------------------------- 오류 → ZabbixError


def test_jsonrpc_error_response_becomes_zabbix_error():
    rec = Recorder(
        lambda r: httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": "Invalid params.",
                    "data": "No permissions.",
                },
                "id": 1,
            },
        )
    )
    with pytest.raises(ZabbixError) as exc:
        real_client(rec).call("host.get", {})
    assert exc.value.code == -32602
    assert exc.value.data == "No permissions."


@pytest.mark.parametrize("status", [401, 403, 500, 502, 503])
def test_http_error_status_becomes_zabbix_error(status):
    rec = Recorder(lambda r: httpx.Response(status, text="oops"))
    with pytest.raises(ZabbixError):
        real_client(rec).call("problem.get", {})


def test_non_json_response_becomes_zabbix_error():
    rec = Recorder(lambda r: httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(ZabbixError):
        real_client(rec).call("problem.get", {})


def test_missing_result_becomes_zabbix_error():
    rec = Recorder(lambda r: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1}))
    with pytest.raises(ZabbixError):
        real_client(rec).call("problem.get", {})


def test_connection_failure_becomes_zabbix_error():
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ZabbixError):
        real_client(Recorder(boom)).call("problem.get", {})


def test_timeout_becomes_zabbix_error():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ZabbixError, match="시간 초과"):
        real_client(Recorder(slow)).call("problem.get", {})


def test_all_errors_share_one_parent():
    assert issubclass(MethodNotAllowed, ZabbixRoError)
    assert issubclass(ZabbixError, ZabbixRoError)


def test_token_is_not_in_error_messages():
    rec = Recorder(lambda r: httpx.Response(500))
    with pytest.raises(ZabbixError) as exc:
        real_client(rec).call("problem.get", {})
    assert TOKEN not in str(exc.value)


# ---------------------------------------------------------------- 설정


@pytest.mark.parametrize("missing", ["ZABBIX_URL", "ZABBIX_API_TOKEN"])
def test_missing_url_or_token_fails_at_call_not_at_creation(missing):
    """Issue #52: Scheduler 는 호출 오류를 잡아 다음 주기에 재시도한다. 만들 때 죽으면 안 된다."""
    env = {"ZABBIX_URL": URL, "ZABBIX_API_TOKEN": TOKEN, "ZABBIX_MOCK": "false"}
    env[missing] = ""
    rec = Recorder()
    client = from_env(env, transport=rec.transport())  # 예외 없이 만들어진다
    assert client.configured is False
    with pytest.raises(ZabbixError, match=missing):
        client.call("problem.get", {})
    assert rec.requests == []  # 요청은 나가지 않았다


def test_empty_environment_creates_client_without_raising():
    client = from_env({})
    assert client.mock is False and client.configured is False
    with pytest.raises(ZabbixRoError):
        client.call("problem.get", {})


@pytest.mark.safety_regression
def test_allowlist_is_checked_before_missing_config():
    """설정이 비어 있어도 쓰기 메서드는 MethodNotAllowed 가 먼저다."""
    with pytest.raises(MethodNotAllowed):
        from_env({}).call("host.update", {})


def test_configured_flag():
    assert from_env({"ZABBIX_MOCK": "true"}).configured is True
    full = {"ZABBIX_URL": URL, "ZABBIX_API_TOKEN": TOKEN}
    assert from_env(full, transport=Recorder().transport()).configured is True


def test_mock_mode_needs_no_url_or_token():
    client = from_env({"ZABBIX_MOCK": "true"})
    assert client.mock is True


def test_from_env_reads_os_environ(monkeypatch):
    monkeypatch.setenv("ZABBIX_MOCK", "true")
    monkeypatch.delenv("ZABBIX_URL", raising=False)
    assert from_env().mock is True


def test_scheduler_interface_names_exist():
    """Issue #52: Scheduler 가 쓰는 이름 (from_env, client.call, 예외 3종)."""
    assert callable(zabbix_ro.from_env)
    assert callable(zabbix_ro.from_env({"ZABBIX_MOCK": "true"}).call)
    for name in ("MethodNotAllowed", "ZabbixError", "ZabbixRoError"):
        assert hasattr(zabbix_ro, name)
