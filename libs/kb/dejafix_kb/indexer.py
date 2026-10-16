"""색인 한 번: 수집 → 저장(증분) → 임베딩(설정돼 있을 때만). knowledge.db 의 유일한 작성자."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from .config import KbSettings
from .embed import EmbedError, EmbedSettings, Embedder, HttpEmbedder, embed_missing
from .sources import collect, now_iso
from .store import counts, open_kb, upsert

log = logging.getLogger("dejafix.kb")


def run_index(
    settings: KbSettings,
    embedder: Embedder | None = None,
    embed_settings: EmbedSettings | None = None,
    only_types: set[str] | None = None,
) -> dict[str, Any]:
    """색인 1회. only_types 를 주면 그 출처만 다시 모은다(예: 해결 메모만 — 저장 직후 빠른 반영, NFR-RAG-003).

    부분 색인에서는 다른 출처를 지우지 않는다(prune 은 이번에 모은 종류에만 적용).
    """
    conn = open_kb(settings.path(settings.kb_db_path))
    try:
        docs = collect(settings)
        if only_types:
            docs = [d for d in docs if d.source_type in only_types]
        stats = upsert(conn, docs)
        result: dict[str, Any] = {
            "index": asdict(stats),
            "embedded_now": 0,
            "embed_error": None,
        }
        es = embed_settings or EmbedSettings.from_env()
        if embedder is None and es.enabled:
            embedder = HttpEmbedder(es)
        if embedder is not None:
            try:
                result["embedded_now"] = embed_missing(conn, embedder, es.pause_sec)
            except EmbedError as exc:
                # 임베딩이 실패해도 키워드 검색은 된다. 다음 색인 때 다시 채운다.
                result["embed_error"] = str(exc)
                log.warning("임베딩 실패 — 키워드 검색만 사용: %s", exc)
        result["counts"] = counts(conn)
        result["indexed_at"] = now_iso()
        key = "last_index_partial_at" if only_types else "last_index_full_at"
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO kb_meta(key, value) VALUES (?, ?)",
                (key, result["indexed_at"]),
            )
        return result
    finally:
        conn.close()
