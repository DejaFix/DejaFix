"""API 28·29 화면에서 Zabbix 연결 (contracts/api.md #28·#29, 결정 018).

저장 전에 그 주소·토큰으로 조회해 보고, 실패하면 저장하지 않는다. 토큰은 어떤 응답에도 없다.
저장하면 Backend Zabbix 호출이 새 연결을 쓴다. 관리자만.
"""

import json

import httpx
import pytest

import zabbix_ro
from dejafix_backend import zabbix
from dejafix_backend.config import get_settings

URL = "https://zbx.customer.example/api_jsonrpc.php"
TOKEN = "cust-read-token-123"


class FakeZabbixHttp:
    """Zabbix JSON-RPC 흉내. 토큰이 맞아야 host.get 이 된다."""

    def __init__(self):
        self.calls = []
        self.good_token = TOKEN

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(
            (str(request.url), body["method"], request.headers.get("authorization"))
        )
        if body["method"] == "apiinfo.version":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "result": "7.0.0", "id": body["id"]}
            )
        if request.headers.get("authorization") != f"Bearer {self.good_token}":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32602,
                        "message": "Invalid params.",
                        "data": "Not authorized.",
                    },
                    "id": body["id"],
                },
            )
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "result": [{"hostid": "1"}], "id": body["id"]}
        )


@pytest.fixture
def zbx(monkeypatch):
    fake = FakeZabbixHttp()
    real = zabbix_ro.from_env

    def from_env(env=None, *, transport=None):
        return real(env, transport=transport or httpx.MockTransport(fake.handle))

    monkeypatch.setattr(zabbix_ro, "from_env", from_env)
    zabbix.reset()
    yield fake
    zabbix.reset()


@pytest.fixture
def admin(make_client, helpers, tmp_path):
    client = make_client(
        zabbix_connection_file=str(tmp_path / "zbx.json"), zabbix_mock="false"
    )
    return client, helpers.login(client, "admin", helpers.admin_password)


def test_before_setup_source_is_env_or_none(admin, zbx):
    client, headers = admin
    res = client.get("/api/settings/zabbix", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["source"] in ("env", "none")
    assert "token" not in data


def test_save_checks_then_stores_and_backend_uses_it(admin, zbx, tmp_path):
    client, headers = admin
    res = client.put(
        "/api/settings/zabbix", json={"url": URL, "token": TOKEN}, headers=headers
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["source"] == "file" and data["url"] == URL and data["token_set"] is True
    assert data["updated_by"] == "admin" and data["verify_tls"] is True
    assert TOKEN not in res.text
    # 저장 전 확인: 버전(인증 없이) + host.get(토큰)
    assert [m for _, m, _ in zbx.calls] == ["apiinfo.version", "host.get"]
    saved = zabbix_ro.read_connection(tmp_path / "zbx.json")
    assert saved["url"] == URL and saved["token"] == TOKEN
    # 이제 Backend 의 Zabbix 호출이 새 연결로 간다
    zbx.calls.clear()
    client.get("/api/problems", headers=headers)
    assert zbx.calls and all(u == URL for u, _, _ in zbx.calls)
    assert any(a == f"Bearer {TOKEN}" for _, _, a in zbx.calls)


def test_bad_token_is_not_saved_and_not_echoed(admin, zbx, tmp_path):
    client, headers = admin
    res = client.put(
        "/api/settings/zabbix",
        json={"url": URL, "token": "wrong-token-zzz"},
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "ZABBIX_CHECK_FAILED"
    assert "wrong-token-zzz" not in res.text
    assert not (tmp_path / "zbx.json").exists()


def test_empty_token_reuses_saved_one(admin, zbx):
    client, headers = admin
    assert (
        client.put(
            "/api/settings/zabbix", json={"url": URL, "token": TOKEN}, headers=headers
        ).status_code
        == 200
    )
    other = "https://zbx2.customer.example/api_jsonrpc.php"
    res = client.put(
        "/api/settings/zabbix", json={"url": other, "token": ""}, headers=headers
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["url"] == other


def test_first_save_needs_a_token(admin, zbx):
    client, headers = admin
    res = client.put(
        "/api/settings/zabbix", json={"url": URL, "token": ""}, headers=headers
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("url", ["ftp://zbx/api", "zbx.example/api_jsonrpc.php"])
def test_url_must_be_http(admin, zbx, url):
    client, headers = admin
    res = client.put(
        "/api/settings/zabbix", json={"url": url, "token": TOKEN}, headers=headers
    )
    assert res.status_code == 422
    assert zbx.calls == []


def test_only_admin(make_client, helpers, zbx):
    client = make_client()
    oncall = helpers.login(client, "oncall", helpers.oncall_password)
    assert client.get("/api/settings/zabbix", headers=oncall).status_code == 403
    assert (
        client.put(
            "/api/settings/zabbix", json={"url": URL, "token": TOKEN}, headers=oncall
        ).status_code
        == 403
    )
    assert client.get("/api/settings/zabbix").status_code == 401


def test_default_path_is_next_to_backend_db(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_DB_PATH", str(tmp_path / "data" / "backend.db"))
    monkeypatch.delenv("ZABBIX_CONNECTION_FILE", raising=False)
    get_settings.cache_clear()
    try:
        assert (
            get_settings().zabbix_connection_path
            == tmp_path / "data" / "zabbix_connection.json"
        )
    finally:
        get_settings.cache_clear()
