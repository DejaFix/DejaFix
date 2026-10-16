"""FR-RAG-007 분석 시 과거 유사 사례 첨부 (결정 017, contracts/mcp-tools.md 6장)."""

import pytest

from dejafix_agent import fallback
from dejafix_agent.collect import collect
from dejafix_agent.config import Settings
from dejafix_agent.main import make_tool_client
from dejafix_agent.tools import (
    ALLOWED_TOOLS,
    ForbiddenToolError,
    RoutedToolClient,
    UnavailableToolClient,
    check_tool_list,
)

T = "2026-10-16T07:00:00Z"
HIT = {
    "chunk_id": "kb_1a2b3c4d5e6f",
    "source_type": "incident_report",
    "source_id": "incident:32",
    "title": "장애 #32 CPU 1분 평균 85% 초과",
    "meta": {"host_name": "TaeYoon-PC"},
}


class Zbx:
    def __init__(self):
        self.calls = []

    def list_tools(self):
        return ["zabbix_get_problem"]

    def call(self, tool, args):
        self.calls.append(tool)
        return {"ok": True, "collected_at": T, "data": {}}


class Kb:
    def __init__(self, hits):
        self.hits = hits
        self.args = None

    def list_tools(self):
        return ["kb_search_knowledge"]

    def call(self, tool, args):
        self.args = args
        return {
            "ok": True,
            "collected_at": T,
            "data": {"mode": "hybrid", "hits": self.hits},
        }


INC = {
    "id": 34,
    "zabbix_eventid": "1",
    "hostid": "10",
    "title": "CPU 과부하",
    "host_name": "Heon-PC",
}


def test_kb_tool_is_in_allowlist_and_check_passes():
    assert "kb_search_knowledge" in ALLOWED_TOOLS
    check_tool_list(["zabbix_get_problem", "kb_search_knowledge"])


def test_routed_client_sends_kb_tools_to_kb_only():
    zbx, kb = Zbx(), Kb([HIT])
    client = RoutedToolClient(zbx, kb)
    assert client.list_tools() == ["zabbix_get_problem", "kb_search_knowledge"]
    client.call("kb_search_knowledge", {"query": "x"})
    assert zbx.calls == [] and kb.args == {"query": "x"}
    with pytest.raises(ForbiddenToolError):
        client.call("zabbix_update_host", {})


def test_collect_adds_kb_call_excluding_current_incident(test_pack):
    kb = Kb([HIT])
    calls = collect(INC, RoutedToolClient(Zbx(), kb), test_pack)
    last = calls[-1]
    assert last.tool == "kb_search_knowledge" and last.ok
    assert kb.args["exclude_source_ids"] == ["incident:34"] and kb.args["k"] == 3
    assert "CPU 과부하" in kb.args["query"] and "Heon-PC" in kb.args["query"]
    assert "결과 1건" in last.summary


def test_collect_without_kb_is_unchanged(test_pack):
    calls = collect(INC, Zbx(), test_pack)
    assert all(c.tool != "kb_search_knowledge" for c in calls)


def test_fallback_report_has_similar_case_fact_with_evidence(test_pack):
    calls = collect(INC, RoutedToolClient(Zbx(), Kb([HIT])), test_pack)
    draft = fallback.build_draft(INC, calls, test_pack)
    fact = next(
        f for f in draft["report"]["facts"] if f["label"] == fallback.KB_FACT_LABEL
    )
    assert "kb_1a2b3c4d5e6f" in fact["value"] and "TaeYoon-PC" in fact["value"]
    assert fact["evidence_ids"] == [calls[-1].id]


def test_no_hits_means_no_fact(test_pack):
    calls = collect(INC, RoutedToolClient(Zbx(), Kb([])), test_pack)
    assert fallback.kb_fact(calls) is None


def test_make_tool_client_routes_only_when_kb_url_set():
    base = {"SHARED_DB_PATH": "x.db"}
    assert isinstance(make_tool_client(Settings.from_env(base)), UnavailableToolClient)
    client = make_tool_client(
        Settings.from_env({**base, "MCP_KB_URL": "http://kb:8300/mcp"})
    )
    assert isinstance(client, RoutedToolClient)


def test_per_server_allowlists():
    import asyncio

    from dejafix_agent.mcp_client import startup_check
    from dejafix_agent.tools import KB_SERVER_TOOLS, ZABBIX_SERVER_TOOLS

    class Lists:
        def __init__(self, names):
            self.names = names

        def list_tools(self):
            return self.names

    # mcp-kb 가 zabbix 도구를 내놓으면 기동 거부
    with pytest.raises(ForbiddenToolError):
        asyncio.run(
            startup_check(
                Lists(["kb_search_knowledge", "zabbix_get_history"]), KB_SERVER_TOOLS
            )
        )
    # mcp-zabbix 가 kb 도구를 내놓아도 기동 거부
    with pytest.raises(ForbiddenToolError):
        asyncio.run(
            startup_check(
                Lists(["zabbix_get_problem", "kb_search_knowledge"]),
                ZABBIX_SERVER_TOOLS,
            )
        )
    asyncio.run(startup_check(Lists(["kb_search_knowledge"]), KB_SERVER_TOOLS))
    asyncio.run(startup_check(Lists(["zabbix_get_problem"]), ZABBIX_SERVER_TOOLS))


def test_kb_client_built_with_kb_only_allowlist():
    from dejafix_agent.tools import KB_SERVER_TOOLS, ZABBIX_SERVER_TOOLS

    client = make_tool_client(
        Settings.from_env(
            {
                "SHARED_DB_PATH": "x.db",
                "MCP_ZABBIX_URL": "http://z:8200/mcp",
                "MCP_KB_URL": "http://kb:8300/mcp",
            }
        )
    )
    assert (
        client.kb.allowed == KB_SERVER_TOOLS
        and client.main.allowed == ZABBIX_SERVER_TOOLS
    )


def test_kb_exception_reason_is_kb_error(test_pack):
    class Boom(Kb):
        def call(self, tool, args):
            raise RuntimeError("down")

    calls = collect(INC, RoutedToolClient(Zbx(), Boom([])), test_pack)
    assert calls[-1].result["reason"] == "KB_ERROR" and not calls[-1].ok
