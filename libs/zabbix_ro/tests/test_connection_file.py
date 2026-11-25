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
