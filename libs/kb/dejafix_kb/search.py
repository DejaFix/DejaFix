"""하이브리드 검색 (FR-RAG-005). 읽기 전용 연결로만 조회한다.

- 키워드: FTS5 trigram(3글자 이상 단어). 2글자 이하 단어는 LIKE 로 보충한다.
- 벡터: 질문을 한 번 임베딩해 저장된 청크 벡터와 코사인 유사도(정규화돼 있으므로 내적).
- 합산: 두 순위를 RRF(1/(K+순위))로 합쳐 상위 k개.
- 기준 미달이면 결과 없음: 키워드에 안 걸리고 코사인도 MIN_COSINE 미만인 청크는 버린다(지어내지 않음).
- 필터: source_type, host_name(장애 리포트 meta), 제외할 source_id(지금 장애 자신).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from .embed import EmbedError, Embedder, from_blob

DEFAULT_K = 5
MIN_COSINE = 0.65
RRF_K = 60
SNIPPET_CHARS = 600

_WORD = re.compile(r"[\w%.:-]+", re.UNICODE)


@dataclass
class Hit:
    chunk_id: str
    source_type: str
    source_id: str
    title: str
    heading: str
    text: str
    score: float
    keyword_rank: int | None = None
    cosine: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "title": self.title,
            "heading": self.heading,
            "text": self.text[:SNIPPET_CHARS],
            "score": round(self.score, 4),
            "keyword_rank": self.keyword_rank,
            "cosine": None if self.cosine is None else round(self.cosine, 4),
            "meta": self.meta,
        }


def _terms(query: str) -> tuple[list[str], list[str]]:
    words = [w for w in _WORD.findall(query) if w.strip()]
    long = [w for w in words if len(w) >= 3]
    short = [w for w in words if len(w) < 3]
    return long, short


def _filters_sql(
    source_types: list[str] | None, exclude: list[str] | None
) -> tuple[str, list]:
    sql, args = "", []
    if source_types:
        sql += f" AND c.source_type IN ({','.join('?' * len(source_types))})"
        args += source_types
    if exclude:
        sql += f" AND c.source_id NOT IN ({','.join('?' * len(exclude))})"
        args += exclude
    return sql, args


def keyword_ranks(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None = None,
    exclude: list[str] | None = None,
    limit: int = 50,
) -> list[str]:
    long, short = _terms(query)
    where, args = _filters_sql(source_types, exclude)
    ids: list[str] = []
    if long:
        match = " OR ".join('"' + w.replace('"', '""') + '"' for w in long)
        rows = conn.execute(
            "SELECT c.chunk_id FROM kb_chunks_fts f JOIN kb_chunks c ON c.chunk_id = f.chunk_id "
            f"WHERE kb_chunks_fts MATCH ? {where} ORDER BY bm25(kb_chunks_fts) LIMIT ?",
            [match, *args, limit],
        ).fetchall()
        ids += [r[0] for r in rows]
    for w in short:
        rows = conn.execute(
            f"SELECT c.chunk_id FROM kb_chunks c WHERE (c.text LIKE ? OR c.title LIKE ?) {where} LIMIT ?",
            [f"%{w}%", f"%{w}%", *args, limit],
        ).fetchall()
        ids += [r[0] for r in rows if r[0] not in ids]
    return ids[:limit]


def vector_scores(
    conn: sqlite3.Connection,
    qvec: list[float],
    source_types: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict[str, float]:
    where, args = _filters_sql(source_types, exclude)
    rows = conn.execute(
        f"SELECT c.chunk_id, c.embedding FROM kb_chunks c WHERE c.embedding IS NOT NULL {where}",
        args,
    ).fetchall()
    out = {}
    for cid, blob in rows:
        vec = from_blob(blob)
        if len(vec) == len(qvec):
            out[cid] = sum(a * b for a, b in zip(vec, qvec))
    return out


def search(
    conn: sqlite3.Connection,
    query: str,
    k: int = DEFAULT_K,
    embedder: Embedder | None = None,
    source_types: list[str] | None = None,
    host_name: str | None = None,
    exclude_source_ids: list[str] | None = None,
    min_cosine: float = MIN_COSINE,
) -> tuple[list[Hit], dict[str, Any]]:
    """(결과, 진단 정보). 결과가 비면 호출자는 '관련 지식 없음'으로 답한다."""
    info: dict[str, Any] = {"mode": "keyword", "embed_error": None}
    kw = keyword_ranks(conn, query, source_types, exclude_source_ids)
    cos: dict[str, float] = {}
    if embedder is not None and query.strip():
        try:
            qvec = embedder.embed([query])[0]
            cos = vector_scores(conn, qvec, source_types, exclude_source_ids)
            info["mode"] = "hybrid"
        except EmbedError as exc:
            info["embed_error"] = str(exc)  # 키워드 검색만으로 계속
    scores: dict[str, float] = {}
    for rank, cid in enumerate(kw, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    vec_ranked = [
        cid for cid, c in sorted(cos.items(), key=lambda x: -x[1]) if c >= min_cosine
    ]
    for rank, cid in enumerate(vec_ranked, start=1):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    if not scores:
        return [], info
    ordered = sorted(scores.items(), key=lambda x: -x[1])
    hits: list[Hit] = []
    kw_pos = {cid: i for i, cid in enumerate(kw, start=1)}
    for cid, score in ordered:
        row = conn.execute(
            "SELECT chunk_id, source_type, source_id, title, heading, text, meta_json FROM kb_chunks WHERE chunk_id = ?",
            (cid,),
        ).fetchone()
        meta = json.loads(row["meta_json"] or "{}")
        if (
            host_name
            and row["source_type"] == "incident_report"
            and meta.get("host_name") != host_name
        ):
            continue
        hits.append(
            Hit(
                row["chunk_id"],
                row["source_type"],
                row["source_id"],
                row["title"],
                row["heading"],
                row["text"],
                score,
                kw_pos.get(cid),
                cos.get(cid),
                meta,
            )
        )
        if len(hits) >= k:
            break
    return hits, info
