"""DR-RAG-001 지식 저장소."""

from dejafix_kb.sources import SourceDoc, collect
from dejafix_kb.store import counts, open_kb, upsert


def d(source_id, text, source_type="runbook"):
    return SourceDoc(source_type, source_id, source_id, text)


def test_schema_is_idempotent(tmp_path):
    p = tmp_path / "k.db"
    open_kb(p).close()
    conn = open_kb(p)
    names = {
        r[0]
        for r in conn.execute("select name from sqlite_master where type in ('table')")
    }
    assert {"kb_documents", "kb_chunks", "kb_meta", "kb_chunks_fts"} <= names


def test_incremental_upsert(tmp_path):
    conn = open_kb(tmp_path / "k.db")
    s1 = upsert(conn, [d("a.md", "# A\n하나"), d("b.md", "# B\n두번째")])
    assert (s1.added, s1.updated, s1.unchanged) == (2, 0, 0)
    s2 = upsert(conn, [d("a.md", "# A\n하나"), d("b.md", "# B\n바뀐내용")])
    assert (s2.added, s2.updated, s2.unchanged) == (0, 1, 1)
    fts = conn.execute(
        "select count(*) from kb_chunks_fts where kb_chunks_fts match '바뀐내용'"
    ).fetchone()[0]
    assert fts == 1
    assert (
        conn.execute(
            "select count(*) from kb_chunks_fts where kb_chunks_fts match '두번째'"
        ).fetchone()[0]
        == 0
    )


def test_prune_removes_missing_docs_but_keeps_notes(tmp_path):
    conn = open_kb(tmp_path / "k.db")
    upsert(
        conn,
        [
            d("a.md", "# A\n1"),
            d("b.md", "# B\n2"),
            d("note:1", "메모", "resolution_note"),
        ],
    )
    s = upsert(conn, [d("a.md", "# A\n1")])
    assert s.removed == 1
    ids = {r[0] for r in conn.execute("select source_id from kb_documents")}
    assert ids == {"a.md", "note:1"}
    assert (
        conn.execute("select count(*) from kb_chunks_fts").fetchone()[0]
        == counts(conn)["chunks"]
    )


def test_trigram_korean_substring(tmp_path):
    conn = open_kb(tmp_path / "k.db")
    upsert(conn, [d("x.md", "# 디스크\n드라이브 사용량이 90%를 넘었습니다")])
    hits = conn.execute(
        "select chunk_id from kb_chunks_fts where kb_chunks_fts match ?", ("사용량",)
    ).fetchall()
    assert len(hits) == 1


def test_index_real_sources(settings):
    conn = open_kb(settings.kb_db_path)
    stats = upsert(conn, collect(settings))
    c = counts(conn)
    assert stats.added == c["documents"] and c["chunks"] >= c["documents"]
    assert c["embedded"] == 0
