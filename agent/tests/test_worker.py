"""분석 워커·고정 수집·fallback (FR-AG-001·002·003·007·008·023, SAFE-03·06)."""

import json

import pytest
from fastapi.testclient import TestClient

from dejafix_agent import worker
from dejafix_agent.config import Settings
from dejafix_agent.llm import LlmError
from dejafix_agent.main import create_app
from dejafix_agent.tools import ForbiddenToolError, UnavailableToolClient
from shared_db import open_db

T = "2026-10-15T01:20:00Z"
CLOCK = 1792027170  # 2026-10-15T01:19:30Z


class FakeMcp:
    def __init__(self, tools=None):
        self.calls = []
        self.tools = tools or [
            "zabbix_get_problem",
            "zabbix_get_host",
            "zabbix_list_items",
            "zabbix_get_history",
        ]

    def list_tools(self):
        return self.tools

    def call(self, tool, args):
        self.calls.append((tool, args))
        env = {"ok": True, "collected_at": T}
        if tool == "zabbix_get_problem":
            return {
                **env,
                "data": {
                    "eventid": args["eventid"],
                    "items": [{"itemid": "45123", "key_": "probe.temp"}],
                },
            }
        if tool == "zabbix_get_host":
            return {**env, "data": {"hostid": args["hostid"], "maintenance": False}}
        if tool == "zabbix_list_items":
            return {
                **env,
                "data": [
                    {
                        "itemid": "45123",
                        "key_": "probe.temp",
                        "name": "Temp",
                        "lastvalue": "96.1",
                        "lastclock": CLOCK,
                        "units": "C",
                    },
                    {
                        "itemid": "45124",
                        "key_": "probe.db[mic1]",
                        "name": "Noise",
                        "lastvalue": "40",
                        "lastclock": CLOCK - 3600,
                        "units": "dB",
                        "stale": True,
                    },
                    {
                        "itemid": "9",
                        "key_": "other.key",
                        "name": "x",
                        "lastvalue": "1",
                        "lastclock": CLOCK,
                    },
                ],
            }
        if tool == "zabbix_get_history":
            return {**env, "data": [{"clock": CLOCK, "value": "96.1"}]}
        return {"ok": False, "reason": "NOT_FOUND"}


@pytest.fixture
def db(settings):
    conn = open_db(settings.shared_db_path, "shared")
    yield conn
    conn.close()


def add_incident(conn, iid, severity=4, status="problem"):
    conn.execute(
        """INSERT INTO incidents(id, zabbix_eventid, zabbix_triggerid, hostid, host_name, title, severity,
               status, started_at, first_seen_at, last_seen_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            iid,
            f"ev{iid}",
            "t1",
            "10584",
            "LAB-PC-07",
            "High temperature",
            severity,
            status,
            T,
            T,
            T,
        ),
    )
    conn.commit()


def one(conn, sql, *args):
    return conn.execute(sql, args).fetchone()


def test_fallback_flow_end_to_end(db, settings, test_pack):
    add_incident(db, 1)
    mcp = FakeMcp()
    worker.tick(db, settings, test_pack, mcp)

    status, error, model, n = one(
        db, "select status, error, model, tool_call_count from agent_runs"
    )
    assert (status, error, model, n) == ("done", "LLM_NOT_CONFIGURED", None, 4)
    assert [c[0] for c in mcp.calls] == [
        "zabbix_get_problem",
        "zabbix_get_host",
        "zabbix_list_items",
        "zabbix_get_history",
    ]

    kind, causes, facts, unknowns = one(
        db, "select kind, causes_json, facts_json, unknowns_json from analysis_reports"
    )
    assert kind == "fallback" and json.loads(causes) == []
    facts = {f["label"].split(" · ")[0]: f for f in json.loads(facts)}
    assert (
        facts["heat"]["value"] == 96.1
        and facts["heat"]["collected_at"] == "2026-10-15T01:19:30Z"
    )
    assert (
        facts["noise"]["value"] is None and facts["noise"]["unknown_reason"] == "STALE"
    )
    assert {"label": "원인", "reason": "NOT_COLLECTED"} in json.loads(unknowns)

    mode, max_tier = one(db, "select mode, max_tier from change_plans")
    steps = db.execute("select action_id, tier from plan_steps order by seq").fetchall()
    assert mode == "preview" and max_tier == "B"
    assert steps == [("t_look", "A"), ("t_tweak", "B")]  # fallback_plans.heat


def test_low_severity_not_analyzed(db, settings, test_pack):
    add_incident(db, 1, severity=1)
    assert worker.tick(db, settings, test_pack, FakeMcp()) == []
    assert one(db, "select count(*) from agent_runs")[0] == 0


def test_only_one_automatic_run(db, settings, test_pack):
    add_incident(db, 1)
    worker.tick(db, settings, test_pack, FakeMcp())
    worker.tick(db, settings, test_pack, FakeMcp())
    assert one(db, "select count(*) from agent_runs where incident_id = 1")[0] == 1


def test_resolved_incident_is_analyzed(db, settings, test_pack):
    add_incident(db, 1, status="resolved")
    assert len(worker.tick(db, settings, test_pack, FakeMcp())) == 1


def test_mcp_unavailable_still_reports(db, settings, test_pack):
    add_incident(db, 1)
    worker.tick(db, settings, test_pack, UnavailableToolClient())
    assert one(db, "select status from agent_runs")[0] == "done"
    assert one(db, "select count(*) from tool_calls where ok = 0")[0] == 3
    facts = json.loads(one(db, "select facts_json from analysis_reports")[0])
    assert all(
        f["value"] is None and f["unknown_reason"] == "TOOL_ERROR" for f in facts
    )
    steps = db.execute("select action_id, tier from plan_steps").fetchall()
    assert steps == [("t_look", "A")]  # 분류 불가 → A 동작만


def test_fake_llm_mode(db, tmp_path, test_pack):
    s = Settings.from_env(
        {"SHARED_DB_PATH": str(tmp_path / "shared.db"), "LLM_FAKE": "true"}
    )
    add_incident(db, 1)
    worker.tick(db, s, test_pack, FakeMcp())
    assert one(db, "select model, error from agent_runs") == ("fake", None)
    kind, causes = one(db, "select kind, causes_json from analysis_reports")
    causes = json.loads(causes)
    assert (
        kind == "llm" and causes[0]["evidence_ids"] and causes[0]["confidence"] == "low"
    )


def real_settings(tmp_path):
    return Settings.from_env(
        {
            "SHARED_DB_PATH": str(tmp_path / "shared.db"),
            "LLM_API_KEY": "k",
            "LLM_BASE_URL": "http://llm",
            "LLM_MODEL": "m",
        }
    )


def test_llm_timeout_goes_fallback(db, tmp_path, test_pack, monkeypatch):
    def boom(settings, prompt):
        raise LlmError("LLM_TIMEOUT")

    monkeypatch.setattr(worker, "complete_json", boom)
    add_incident(db, 1)
    worker.tick(db, real_settings(tmp_path), test_pack, FakeMcp())
    assert one(db, "select status, error from agent_runs") == ("done", "LLM_TIMEOUT")
    assert one(db, "select kind from analysis_reports")[0] == "fallback"


def test_invalid_llm_draft_goes_fallback(db, tmp_path, test_pack, monkeypatch):
    monkeypatch.setattr(
        worker, "complete_json", lambda s, p: {"report": {"summary": "x"}}
    )
    add_incident(db, 1)
    worker.tick(db, real_settings(tmp_path), test_pack, FakeMcp())
    assert one(db, "select status, error from agent_runs") == ("done", "LLM_ERROR")
    assert one(db, "select kind from analysis_reports")[0] == "fallback"


def test_llm_tier_ignored(db, tmp_path, test_pack, monkeypatch):
    def draft(settings, prompt):
        assert "t_look" in prompt  # 허용 동작 목록이 프롬프트에 들어감 (FR-AG-004)
        return {
            "report": {
                "summary": "s",
                "impact": {
                    "hosts": [],
                    "services": [],
                    "user_impact": None,
                    "evidence_ids": [],
                },
                "causes": [],
                "facts": [],
                "unknowns": [],
                "next_checks": [],
            },
            "plan": {
                "title": "p",
                "goal": None,
                "assumptions": [],
                "steps": [{"action_id": "t_smash", "title": "부수기", "tier": "A"}],
            },
        }

    monkeypatch.setattr(worker, "complete_json", draft)
    add_incident(db, 1)
    worker.tick(db, real_settings(tmp_path), test_pack, FakeMcp())
    assert one(db, "select kind from analysis_reports")[0] == "llm"
    assert db.execute("select tier from plan_steps").fetchall() == [("C",)]


def test_forbidden_mcp_tool_blocks_startup(settings, packs_dir):
    bad = FakeMcp(tools=["zabbix_get_problem", "zabbix_update_host"])
    with pytest.raises(ForbiddenToolError):
        with TestClient(
            create_app(settings, packs_dir, tool_client=bad, start_worker=False)
        ):
            pass
