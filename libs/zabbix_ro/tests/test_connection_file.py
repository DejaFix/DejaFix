"""화면에서 정한 Zabbix 연결 파일 (ZABBIX_CONNECTION_FILE) — from_env 가 환경 변수보다 먼저 쓰고,
LiveClient 는 파일이 바뀌면 다음 호출 때 새 연결을 따른다. 토큰은 파일에만 있다."""

import json
import os
import stat
import sys

import httpx
import pytest

import zabbix_ro
from zabbix_ro.connection import overlay

ENV = {"ZABBIX_URL": "http://env-zbx/api_jsonrpc.php", "ZABBIX_API_TOKEN": "env-token"}


def test_no_file_keeps_env(tmp_path):
    env = {**ENV, "ZABBIX_CONNECTION_FILE": str(tmp_path / "none.json")}
    client = zabbix_ro.from_env(env)
    assert client.url == ENV["ZABBIX_URL"]


def test_file_overrides_url_token_tls(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(
        path, " http://cust-zbx/api_jsonrpc.php ", "cust-token", "false", "admin"
    )
    client = zabbix_ro.from_env({**ENV, "ZABBIX_CONNECTION_FILE": str(path)})
    assert client.url == "http://cust-zbx/api_jsonrpc.php"
    assert client.verify_tls is False
    found = zabbix_ro.read_connection(path)
    assert found["token"] == "cust-token" and found["updated_by"] == "admin"
    assert found["updated_at"].endswith("Z")


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX 권한만 본다")
def test_file_is_private(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(path, "http://z", "t")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"url": "", "token": "t"}),
        json.dumps({"url": "http://z"}),
    ],
)
def test_broken_or_empty_file_is_ignored(tmp_path, content):
    path = tmp_path / "zbx.json"
    path.write_text(content, encoding="utf-8")
    assert zabbix_ro.read_connection(path) is None
    assert (
        overlay({**ENV, "ZABBIX_CONNECTION_FILE": str(path)})["ZABBIX_URL"]
        == ENV["ZABBIX_URL"]
    )


def test_live_client_follows_file_changes(tmp_path):
    path = tmp_path / "zbx.json"
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("authorization")))
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": [], "id": 1})

    transport = httpx.MockTransport(handler)
    env = {**ENV, "ZABBIX_CONNECTION_FILE": str(path)}

    def build():
        return zabbix_ro.from_env(env, transport=transport)

    live = zabbix_ro.LiveClient(build, path)
    live.call("host.get", {})
    zabbix_ro.save_connection(path, "http://cust-zbx/api_jsonrpc.php", "cust-token")
    live.call("host.get", {})
    assert seen[0][0] == ENV["ZABBIX_URL"]
    assert seen[1][0] == "http://cust-zbx/api_jsonrpc.php"
    assert seen[1][1] == "Bearer cust-token"


def test_live_client_closes_the_old_client_on_switch(tmp_path):
    """연결이 바뀌면 옛 클라이언트(HTTP 연결 풀)를 닫는다 (리뷰 11/26)."""
    path = tmp_path / "zbx.json"
    built = []

    class Fake:
        def __init__(self):
            self.closed = False

        def call(self, method, params=None):
            return []

        def close(self):
            self.closed = True

    def build():
        built.append(Fake())
        return built[-1]

    live = zabbix_ro.LiveClient(build, path)
    live.call("host.get", {})
    zabbix_ro.save_connection(path, "http://cust-zbx/api_jsonrpc.php", "cust-token")
    live.call("host.get", {})
    assert len(built) == 2
    assert built[0].closed is True and built[1].closed is False


def test_live_client_still_refuses_write_methods(tmp_path):
    live = zabbix_ro.live_from_env(
        {**ENV, "ZABBIX_CONNECTION_FILE": str(tmp_path / "x.json")}
    )
    with pytest.raises(zabbix_ro.MethodNotAllowed):
        live.call("host.update", {})


def test_token_not_in_repr_or_errors(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(
        path, "http://cust-zbx/api_jsonrpc.php", "secret-cust-token"
    )
    client = zabbix_ro.from_env({"ZABBIX_CONNECTION_FILE": str(path)})
    assert "secret-cust-token" not in repr(client)


def test_default_path_is_next_to_db_files(tmp_path):
    from zabbix_ro.connection import connection_path

    assert connection_path({"BACKEND_DB_PATH": str(tmp_path / "d" / "backend.db")}) == (
        tmp_path / "d" / "zabbix_connection.json"
    )
    assert connection_path({"SHARED_DB_PATH": str(tmp_path / "s" / "shared.db")}) == (
        tmp_path / "s" / "zabbix_connection.json"
    )
    assert connection_path(
        {"ZABBIX_CONNECTION_FILE": str(tmp_path / "x.json"), "SHARED_DB_PATH": "a/b.db"}
    ) == (tmp_path / "x.json")
    assert connection_path({}) is None


# ---------- 회사별 (결정 019) ----------

CO = {**ENV, "DEFAULT_COMPANY_ID": "catbooks"}


def _env(path, company=None, **extra):
    env = {**CO, "ZABBIX_CONNECTION_FILE": str(path), **extra}
    if company:
        env["ZABBIX_COMPANY"] = company
    return env


def test_company_file_keeps_other_companies(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(
        path, "http://cb", "cb-t", "", "a", "catbooks", "catbooks"
    )
    zabbix_ro.save_connection(
        path, "http://nubi", "nb-t", "", "b", "c-cf2f0d", "catbooks"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw["companies"]) == {"catbooks", "c-cf2f0d"}
    assert zabbix_ro.from_env(_env(path, "c-cf2f0d")).url == "http://nubi"
    assert zabbix_ro.from_env(_env(path, "catbooks")).url == "http://cb"
    assert zabbix_ro.from_env(_env(path)).url == "http://cb"  # 머리 없음 = 기본 회사
    assert zabbix_ro.connected_companies(path, "catbooks") == ["c-cf2f0d", "catbooks"]


def test_company_without_connection_never_falls_back(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(path, "http://cb", "cb-t")  # 018 모양 = 기본 회사 것
    client = zabbix_ro.from_env(_env(path, "c-cf2f0d", ZABBIX_MOCK="true"))
    assert (
        client.url is None and client.mock is False
    )  # 캣북스 파일·.env·목으로 떨어지지 않는다
    assert zabbix_ro.from_env(_env(path, "catbooks")).url == "http://cb"
    assert (
        zabbix_ro.from_env(_env(tmp_path / "none.json", "catbooks")).url
        == ENV["ZABBIX_URL"]
    )
    assert zabbix_ro.from_env(_env(tmp_path / "none.json", "c-cf2f0d")).url is None


def test_legacy_file_moves_under_default_company_on_save(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(path, "http://cb", "cb-t")
    legacy_id = zabbix_ro.read_connection(path)["conn_id"]
    zabbix_ro.save_connection(
        path, "http://nubi", "nb-t", "", "", "c-cf2f0d", "catbooks"
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["companies"]["catbooks"]["url"] == "http://cb"
    assert (
        raw["companies"]["catbooks"]["conn_id"] == legacy_id
    )  # 캣북스 연결 구분값 그대로


def test_conn_id_changes_only_when_url_changes(tmp_path):
    """준하 님 #216 리뷰: 토큰·verify_tls 만 바뀌면 같은 Zabbix 라 conn_id 그대로."""
    path = tmp_path / "zbx.json"
    save = zabbix_ro.save_connection
    save(path, "http://n", "t1", "", "", "c-cf2f0d", "catbooks")
    first = zabbix_ro.read_connection(path, "c-cf2f0d", "catbooks")["conn_id"]
    assert first.startswith("zc_") and len(first) == 15
    save(path, "http://n", "t2", "false", "other", "c-cf2f0d", "catbooks")
    assert zabbix_ro.read_connection(path, "c-cf2f0d", "catbooks")["conn_id"] == first
    save(path, "http://n2", "t2", "false", "", "c-cf2f0d", "catbooks")
    assert zabbix_ro.read_connection(path, "c-cf2f0d", "catbooks")["conn_id"] != first


def test_file_state(tmp_path):
    path = tmp_path / "zbx.json"
    assert zabbix_ro.connection_file_state(path) == "missing"
    path.write_text("{broken", encoding="utf-8")
    assert zabbix_ro.connection_file_state(path) == "broken"
    zabbix_ro.save_connection(path, "http://n", "t")
    assert zabbix_ro.connection_file_state(path) == "ok"


def test_resolve_gives_env_conn_id_for_default_only(tmp_path):
    none = tmp_path / "none.json"
    conn_id = zabbix_ro.resolve(_env(none))["conn_id"]
    assert conn_id == zabbix_ro.env_conn_id(ENV["ZABBIX_URL"])
    assert conn_id.startswith("env:")
    other = _env(none, ZABBIX_URL="http://other-env-zbx")
    assert zabbix_ro.resolve(other)["conn_id"] != conn_id  # .env 주소가 바뀌어도 가른다
    assert zabbix_ro.resolve(_env(none, "c-cf2f0d")) is None


def test_scoping_off_keeps_018_behaviour(tmp_path):
    path = tmp_path / "zbx.json"
    zabbix_ro.save_connection(path, "http://cb", "cb-t")
    env = {**ENV, "ZABBIX_CONNECTION_FILE": str(path), "ZABBIX_COMPANY": "c-cf2f0d"}
    assert (
        zabbix_ro.from_env(env).url == "http://cb"
    )  # DEFAULT_COMPANY_ID 없으면 회사 무시
