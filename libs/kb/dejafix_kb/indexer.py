"""색인 한 번: 수집 → 저장(증분) → 임베딩(설정돼 있을 때만). knowledge.db 의 유일한 작성자."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from .config import KbSettings
from .embed import EmbedError, EmbedSettings, Embedder, HttpEmbedder, embed_missing
from .sources import collect
from .store import counts, open_kb, upsert

log = logging.getLogger("dejafix.kb")


def run_index(
    settings: KbSettings,
    embedder: Embedder | None = None,
    embed_settings: EmbedSettings | None = None,
) -> dict[str, Any]:
    conn = open_kb(settings.path(settings.kb_db_path))
    try:
        stats = upsert(conn, collect(settings))
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
        return result
    finally:
        conn.close()
