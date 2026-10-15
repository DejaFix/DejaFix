import sqlite3

import pytest
from fastapi.testclient import TestClient

from dejafix_agent.config import Settings
from dejafix_agent.main import _mcp_health_url, create_app
from dejafix_agent.packs import PackError


def test_healthz_fallback_mode(settings, packs_dir):
    with TestClient(create_app(settings, packs_dir)) as client:
        body = client.get("/healthz").json()
    assert body == {"ok": True, "model": None, "mcp": {"zabbix": "down"}}


def test_startup_applies_shared_schema(settings, packs_dir):
    with TestClient(create_app(settings, packs_dir)):
        pass
    conn = sqlite3.connect(settings.shared_db_path)
    names = {
        r[0] for r in conn.execute("select name from sqlite_master where type='table'")
    }
    conn.close()
    assert {"incidents", "agent_runs", "tool_calls", "change_plans"} <= names


def test_startup_fails_without_pack(tmp_path, packs_dir):
    s = Settings.from_env(
        {"SHARED_DB_PATH": str(tmp_path / "s.db"), "DOMAIN_PACK": "missing"}
    )
    with pytest.raises(PackError):
        with TestClient(create_app(s, packs_dir)):
            pass


@pytest.mark.parametrize(
    "env,mode,label",
    [
        ({"LLM_FAKE": "true"}, "fake", "fake"),
        ({}, "fallback", None),
        ({"LLM_API_KEY": "k"}, "fallback", None),
        (
            {"LLM_API_KEY": "k", "LLM_BASE_URL": "http://x", "LLM_MODEL": "m"},
            "real",
            "m",
        ),
    ],
)
def test_llm_mode(env, mode, label):
    s = Settings.from_env(env)
    assert s.llm_mode == mode and s.model_label == label


def test_mcp_health_url():
    assert (
        _mcp_health_url("http://mcp-zabbix:8200/mcp")
        == "http://mcp-zabbix:8200/healthz"
    )
    assert _mcp_health_url("") is None
