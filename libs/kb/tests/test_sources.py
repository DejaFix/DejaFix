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


def _notes_db(path, rows):
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(
        "create table resolution_notes(id integer primary key, incident_id integer, author_user_id integer,"
        " root_cause text, action_taken text, result text, created_at text)"
    )
    conn.executemany(
        "insert into resolution_notes(id, incident_id, author_user_id, root_cause, action_taken, result, created_at)"
        " values (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


def test_note_docs_from_backend_db(tmp_path):
    from dejafix_kb.sources import note_docs

    db = tmp_path / "backend.db"
    _notes_db(
        db,
        [
            (
                1,
                32,
                2,
                "백신 검사 프로세스 폭주",
                "검사 일정 변경",
                "CPU 정상화",
                "2026-10-16T07:00:00Z",
            )
        ],
    )
    docs = note_docs(db)
    assert [d.source_id for d in docs] == ["note:1"]
    assert docs[0].source_type == "resolution_note"
    assert "실제 원인: 백신 검사 프로세스 폭주" in docs[0].text
    assert docs[0].meta == {"incident_id": 32, "note_id": 1}


def test_note_docs_missing_table_or_db(tmp_path):
    import sqlite3

    from dejafix_kb.sources import note_docs

    assert note_docs(tmp_path / "none.db") == []
    db = tmp_path / "backend.db"
    sqlite3.connect(db).close()
    assert note_docs(db) == []


def test_collect_includes_notes(settings, tmp_path):
    from dataclasses import replace

    db = tmp_path / "b.db"
    _notes_db(db, [(7, 1, 2, "원인", "조치", "결과", "2026-10-16T07:00:00Z")])
    docs = collect(replace(settings, backend_db_path=db))
    assert "note:7" in {d.source_id for d in docs}


def test_note_columns_differ_skips_notes_only(settings, tmp_path, caplog):
    """컬럼 이름이 계약과 다르면 해결 메모만 건너뛰고 로그를 남긴다. 장애·런북 색인은 멈추지 않는다 (#155 리뷰 2번)."""
    import logging
    import sqlite3
    from dataclasses import replace

    from dejafix_kb.sources import note_docs

    db = tmp_path / "b.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table resolution_notes(id integer primary key, incident_id integer, cause text, created_at text)"
    )
    conn.execute(
        "insert into resolution_notes values (1, 1, '원인', '2026-10-16T07:00:00Z')"
    )
    conn.commit()
    conn.close()
    with caplog.at_level(logging.WARNING, logger="dejafix_kb.sources"):
        assert note_docs(db) == []
    assert "root_cause" in caplog.text
    docs = collect(replace(settings, backend_db_path=db))
    assert docs and not any(d.source_type == "resolution_note" for d in docs)
