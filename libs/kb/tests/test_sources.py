"""FR-RAG-002 지식 출처 수집기."""

from dejafix_kb.config import KbSettings
from dejafix_kb.sources import collect, incident_docs, pack_docs, runbook_docs


def test_incident_docs_one_per_reported_incident(seeded_shared):
    docs = incident_docs(seeded_shared)
    assert docs, "시드에 리포트가 있는 장애가 있어야 한다"
    ids = [d.source_id for d in docs]
    assert len(ids) == len(set(ids))
    first = docs[0]
    assert first.source_type == "incident_report"
    assert first.text.startswith("# 장애 #")
    assert "리포트 #" in first.text and first.meta["incident_id"]


def test_incident_docs_missing_db_is_empty(tmp_path):
    assert incident_docs(tmp_path / "none.db") == []


def test_runbook_and_pack_docs(settings):
    runbooks = runbook_docs(settings.root, settings.doc_dirs)
    assert any(d.source_id == "docs/demo/README.md" for d in runbooks)
    actions = pack_docs(settings.root, settings.domain_pack)
    assert actions and all(d.source_type == "pack_action" for d in actions)
    assert all("티어" in d.text for d in actions)


def test_pack_docs_need_domain_pack(settings):
    assert pack_docs(settings.root, None) == []


def test_collect_order_and_hash_is_stable(settings):
    docs = collect(settings)
    types = [d.source_type for d in docs]
    assert (
        types.index("incident_report")
        < types.index("runbook")
        < types.index("pack_action")
    )
    again = {d.source_id: d.content_hash for d in collect(settings)}
    assert {d.source_id: d.content_hash for d in docs} == again


def test_collect_does_not_write_shared_db(settings, seeded_shared):
    before = seeded_shared.stat().st_mtime_ns
    collect(settings)
    assert seeded_shared.stat().st_mtime_ns == before


def test_settings_defaults():
    s = KbSettings.from_env({})
    assert s.kb_db_path.as_posix() == "data/knowledge.db"
    assert s.domain_pack is None and s.doc_dirs == ("docs/demo", "docs/zabbix")
