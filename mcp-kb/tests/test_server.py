"""mcp-kb 서버 — tools/list 1개(SAFE-03), 공통 봉투, /healthz, 읽기 전용, 내부 토큰."""

import asyncio
import json

from starlette.testclient import TestClient

from dejafix_kb.sources import SourceDoc
from dejafix_kb.store import open_kb, upsert
from mcp_kb.server import TOOL_NAME, KbSearcher, build_app, build_server

WRITE_MARKERS = ("_create_", "_update_", "_delete_", "_index", "_write", "_set_")


def kb(tmp_path):
    path = tmp_path / "knowledge.db"
    conn = open_kb(path)
    upsert(
        conn,
        [
            SourceDoc(
                "incident_report",
                "incident:1",
                "장애 #1 CPU",
                "# 장애 #1\n- CPU 부하 99% 원인 프로세스 과다",
                meta={"host_name": "A-PC"},
            ),
            SourceDoc(
                "runbook", "docs/x.md", "런북", "# 런북\n디스크 드라이브 정리 절차"
            ),
        ],
    )
    conn.close()
    return path


def call(searcher, args):
    result = asyncio.run(build_server(searcher).call_tool(TOOL_NAME, args))
    assert json.loads(result.content[0].text) == result.structured_content
    return result.structured_content


def test_tools_list_is_exactly_one_read_tool(tmp_path):
    names = [
        t.name
        for t in asyncio.run(build_server(KbSearcher(kb(tmp_path), None)).list_tools())
    ]
    assert names == [TOOL_NAME]
    assert not any(m in names[0] for m in WRITE_MARKERS)


def test_search_envelope_and_hits(tmp_path):
    out = call(KbSearcher(kb(tmp_path), None), {"query": "프로세스 과다", "k": 9})
    assert out["ok"] is True and out["data"]["mode"] == "keyword"
    hits = out["data"]["hits"]
    assert hits and hits[0]["chunk_id"].startswith("kb_") and len(hits) <= 5
    assert hits[0]["source_id"] == "incident:1"


def test_empty_result_is_ok_with_no_hits(tmp_path):
    out = call(KbSearcher(kb(tmp_path), None), {"query": "고양이 사료 추천"})
    assert out["ok"] is True and out["data"]["hits"] == []


def test_missing_db_and_empty_query_are_kb_error(tmp_path):
    out = call(KbSearcher(tmp_path / "none.db", None), {"query": "디스크"})
    assert out["ok"] is False and out["reason"] == "KB_ERROR"
    assert str(tmp_path) not in out["message"]
    out = call(KbSearcher(kb(tmp_path), None), {"query": "  "})
    assert out["reason"] == "KB_ERROR"


def test_unknown_source_type_is_ignored_and_filters_apply(tmp_path):
    s = KbSearcher(kb(tmp_path), None)
    out = call(s, {"query": "디스크 드라이브", "source_types": ["runbook", "bogus"]})
    assert {h["source_type"] for h in out["data"]["hits"]} == {"runbook"}
    out = call(s, {"query": "프로세스 과다", "exclude_source_ids": ["incident:1"]})
    assert "incident:1" not in {h["source_id"] for h in out["data"]["hits"]}


def test_search_does_not_write_db(tmp_path):
    path = kb(tmp_path)
    before = path.stat().st_mtime_ns
    call(KbSearcher(path, None), {"query": "프로세스 과다"})
    assert path.stat().st_mtime_ns == before


def test_healthz(tmp_path):
    client = TestClient(build_app(KbSearcher(kb(tmp_path), None)))
    assert client.get("/healthz").json() == {
        "ok": True,
        "kb": "ok",
        "documents": 2,
        "chunks": 2,
    }
    client = TestClient(build_app(KbSearcher(tmp_path / "none.db", None)))
    assert client.get("/healthz").json()["kb"] == "down"


def test_internal_token(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "t0ken")
    client = TestClient(build_app(KbSearcher(kb(tmp_path), None)))
    assert client.get("/healthz").status_code == 200
    assert client.post("/mcp", json={}).status_code == 401
