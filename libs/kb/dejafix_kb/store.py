"""지식 저장소 knowledge.db (DR-RAG-001). 작성자는 색인기(index) 하나뿐이다.

테이블
- kb_documents: 출처 문서 1개 = 1행 (source_id PK, content_hash 로 변경 감지)
- kb_chunks: 청크 (chunk_id PK = 근거 ID), embedding 은 float32 BLOB (FR-RAG-004 가 채움)
- kb_chunks_fts: FTS5 trigram 색인 (한국어 부분 문자열 검색)
- kb_meta: 임베딩 모델·차원 등

shared.db·backend.db 와 섞지 않는다(별도 파일, contracts/db-schema.sql 밖). 다른 파트는 이 파일을 직접 읽지 않고
MCP 도구 kb_search_knowledge(FR-RAG-006)로만 조회한다.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .chunker import Chunk, chunk_doc
from .sources import SourceDoc, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_documents (
  source_id     TEXT PRIMARY KEY,
  source_type   TEXT NOT NULL CHECK (source_type IN ('incident_report','runbook','pack_action','resolution_note')),
  title         TEXT NOT NULL,
  content_hash  TEXT NOT NULL,
  collected_at  TEXT NOT NULL,
  indexed_at    TEXT NOT NULL,
  meta_json     TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS kb_chunks (
  chunk_id      TEXT PRIMARY KEY,
  source_id     TEXT NOT NULL REFERENCES kb_documents(source_id) ON DELETE CASCADE,
  source_type   TEXT NOT NULL,
  title         TEXT NOT NULL,
  heading       TEXT NOT NULL,
  ordinal       INTEGER NOT NULL,
  text          TEXT NOT NULL,
  tokens        INTEGER NOT NULL,
  meta_json     TEXT NOT NULL DEFAULT '{}',
  embedding     BLOB,
  embed_model   TEXT
);
CREATE INDEX IF NOT EXISTS ix_kb_chunks_source ON kb_chunks(source_id);
CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
  chunk_id UNINDEXED, title, heading, text, tokenize = 'trigram'
);
CREATE TABLE IF NOT EXISTS kb_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_kb(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def open_kb_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@dataclass
class IndexStats:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    chunks_written: int = 0


def _delete_source(conn: sqlite3.Connection, source_id: str) -> None:
    conn.execute(
        "DELETE FROM kb_chunks_fts WHERE chunk_id IN (SELECT chunk_id FROM kb_chunks WHERE source_id = ?)",
        (source_id,),
    )
    conn.execute("DELETE FROM kb_chunks WHERE source_id = ?", (source_id,))
    conn.execute("DELETE FROM kb_documents WHERE source_id = ?", (source_id,))


def _insert_chunks(conn: sqlite3.Connection, chunks: list[Chunk]) -> None:
    for c in chunks:
        conn.execute(
            """INSERT INTO kb_chunks(chunk_id, source_id, source_type, title, heading, ordinal, text, tokens, meta_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                c.chunk_id,
                c.source_id,
                c.source_type,
                c.title,
                c.heading,
                c.ordinal,
                c.text,
                c.tokens,
                json.dumps(c.meta, ensure_ascii=False, default=str),
            ),
        )
        conn.execute(
            "INSERT INTO kb_chunks_fts(chunk_id, title, heading, text) VALUES (?,?,?,?)",
            (c.chunk_id, c.title, c.heading, c.text),
        )


def upsert(
    conn: sqlite3.Connection, docs: list[SourceDoc], prune: bool = True
) -> IndexStats:
    """문서 해시가 같으면 건너뛰고, 바뀌면 그 문서의 청크를 통째로 다시 쓴다.

    prune=True 면 이번 수집에 없는 문서(같은 source_type)는 지운다. 단 사람이 쓴 resolution_note 는 지우지 않는다.
    """
    stats = IndexStats()
    now = now_iso()
    seen: set[str] = set()
    with conn:
        for d in docs:
            seen.add(d.source_id)
            row = conn.execute(
                "SELECT content_hash FROM kb_documents WHERE source_id = ?",
                (d.source_id,),
            ).fetchone()
            if row and row["content_hash"] == d.content_hash:
                stats.unchanged += 1
                continue
            if row:
                _delete_source(conn, d.source_id)
                stats.updated += 1
            else:
                stats.added += 1
            conn.execute(
                """INSERT INTO kb_documents(source_id, source_type, title, content_hash, collected_at, indexed_at, meta_json)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    d.source_id,
                    d.source_type,
                    d.title,
                    d.content_hash,
                    d.collected_at,
                    now,
                    json.dumps(d.meta, ensure_ascii=False, default=str),
                ),
            )
            chunks = chunk_doc(d)
            _insert_chunks(conn, chunks)
            stats.chunks_written += len(chunks)
        if prune:
            types = {d.source_type for d in docs} - {"resolution_note"}
            for t in types:
                for r in conn.execute(
                    "SELECT source_id FROM kb_documents WHERE source_type = ?", (t,)
                ).fetchall():
                    if r["source_id"] not in seen:
                        _delete_source(conn, r["source_id"])
                        stats.removed += 1
    return stats


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {
        "documents": conn.execute("SELECT COUNT(*) FROM kb_documents").fetchone()[0],
        "chunks": conn.execute("SELECT COUNT(*) FROM kb_chunks").fetchone()[0],
        "embedded": conn.execute(
            "SELECT COUNT(*) FROM kb_chunks WHERE embedding IS NOT NULL"
        ).fetchone()[0],
    }
