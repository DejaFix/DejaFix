"""NFR-RAG-003 재색인: 전체(일일)·해결 메모만(즉시) 부분 색인, 마지막 색인 시각."""

import sqlite3
from dataclasses import replace

from dejafix_kb.embed import EmbedSettings
from dejafix_kb.indexer import run_index
from dejafix_kb.store import open_kb

OFF = EmbedSettings("", "", "", 768)


def _notes(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        "create table if not exists resolution_notes(id integer primary key, incident_id integer,"
        " author_user_id integer, root_cause text, action_taken text, result text, created_at text)"
    )
    conn.executemany("insert into resolution_notes values (?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_full_then_notes_only(settings, tmp_path):
    b = tmp_path / "backend.db"
    s = replace(settings, backend_db_path=b)
    full = run_index(s, embed_settings=OFF)
    docs_before = full["counts"]["documents"]
    _notes(b, [(1, 1, 2, "원인", "조치", "결과", "2026-10-16T08:00:00Z")])
    part = run_index(s, embed_settings=OFF, only_types={"resolution_note"})
    assert part["index"]["added"] == 1 and part["index"]["removed"] == 0
    assert part["counts"]["documents"] == docs_before + 1  # 다른 출처는 지우지 않음
    conn = open_kb(s.kb_db_path)
    meta = dict(conn.execute("select key, value from kb_meta").fetchall())
    assert "last_index_full_at" in meta and "last_index_partial_at" in meta


def test_rerun_full_is_incremental(settings):
    run_index(settings, embed_settings=OFF)
    again = run_index(settings, embed_settings=OFF)
    assert again["index"]["added"] == 0 and again["index"]["updated"] == 0
    assert again["index"]["unchanged"] == again["counts"]["documents"]


def test_partial_runbook_only_keeps_incidents_and_prunes_removed_runbooks(
    settings, tmp_path
):
    """부분 색인은 고른 종류 안에서만 정리한다: 없어진 런북은 지우고, 장애·팩 문서는 그대로 (#160)."""
    root = tmp_path / "repo"
    ops = root / "docs" / "ops"
    ops.mkdir(parents=True)
    (ops / "a.md").write_text("# A\n런북 A", encoding="utf-8")
    (ops / "b.md").write_text("# B\n런북 B", encoding="utf-8")
    s = replace(settings, root=root, doc_dirs=("docs/ops",), domain_pack=None)

    def by_type():
        conn = open_kb(s.kb_db_path)
        try:
            return dict(
                conn.execute(
                    "select source_type, count(*) from kb_documents group by 1"
                ).fetchall()
            )
        finally:
            conn.close()

    run_index(s, embed_settings=OFF)
    before = by_type()
    assert before["runbook"] == 2 and before["incident_report"] > 0
    (ops / "b.md").unlink()  # tmp_path 안의 사본만 지운다
    part = run_index(s, embed_settings=OFF, only_types={"runbook"})
    assert part["index"]["removed"] == 1
    after = by_type()
    assert after["runbook"] == 1
    assert after["incident_report"] == before["incident_report"]


def test_partial_falls_back_to_full_when_chunker_changed(settings):
    """청킹 규칙 버전이 다르면 부분 색인이 다른 출처를 비운 채 끝나지 않고 전체로 다시 쓴다."""
    full = run_index(settings, embed_settings=OFF)
    conn = open_kb(settings.kb_db_path)
    with conn:
        conn.execute("update kb_meta set value = 'old' where key = 'chunker_version'")
    conn.close()
    part = run_index(settings, embed_settings=OFF, only_types={"resolution_note"})
    assert part["counts"]["documents"] == full["counts"]["documents"]
