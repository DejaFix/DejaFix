"""RAG 평가 (NFR-RAG-002). python -m dejafix_kb eval [질의셋.yaml]

지표
- Recall@5: 정답이 있는 질의 중 상위 5개에 기대 출처가 하나라도 있는 비율
- 인용 정확도: 정답이 있는 질의의 상위 결과 중 기대 출처와 맞는 결과 비율(평균)
- 관련 없음 정확도: 정답이 없는 질의(expect: [])에서 결과가 0건인 비율 — 지어내지 않는지
- 검색 응답 시간: 질의마다 임베딩 포함 경과 시간(평균·최대), 목표 3초 이내
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from .embed import Embedder
from .search import search

# 질의셋은 도메인 데이터(동작 ID·장애 제목)라 팩에 둔다: packs/${DOMAIN_PACK}/kb-eval.yaml (⑨-1)
PACK_QUERIES = "kb-eval.yaml"
K = 5
LATENCY_TARGET_SEC = 3.0


def _match(hit: dict[str, Any], expect: list[str]) -> bool:
    hay = f"{hit['title']}\n{hit['source_id']}"
    return any(e in hay for e in expect)


def pack_queries_path(root: Path, domain_pack: str | None) -> Path | None:
    """활성 팩의 질의셋 경로. 팩이 없으면 None(호출자가 경로를 직접 줘야 한다)."""
    return root / "packs" / domain_pack / PACK_QUERIES if domain_pack else None


def run_eval(
    conn, embedder: Embedder | None, queries_path: Path
) -> dict[str, Any]:
    data = yaml.safe_load(queries_path.read_text(encoding="utf-8")) or {}
    rows = []
    for item in data.get("queries") or []:
        q, expect = item["q"], list(item.get("expect") or [])
        t0 = time.perf_counter()
        hits, info = search(conn, q, K, embedder)
        sec = time.perf_counter() - t0
        hd = [h.to_dict() for h in hits]
        matched = [_match(h, expect) for h in hd] if expect else []
        rows.append(
            {
                "q": q,
                "expect": expect,
                "hits": len(hd),
                "top": [h["source_id"] for h in hd],
                "recall": bool(any(matched)) if expect else None,
                "precision": (sum(matched) / len(hd))
                if (expect and hd)
                else (0.0 if expect else None),
                "no_answer_ok": (len(hd) == 0) if not expect else None,
                "sec": round(sec, 3),
                "mode": info["mode"],
            }
        )
    pos = [r for r in rows if r["expect"]]
    neg = [r for r in rows if not r["expect"]]
    secs = [r["sec"] for r in rows]
    summary = {
        "queries": len(rows),
        "recall_at_5": round(sum(r["recall"] for r in pos) / len(pos), 3)
        if pos
        else None,
        "citation_precision": round(sum(r["precision"] for r in pos) / len(pos), 3)
        if pos
        else None,
        "no_answer_accuracy": round(sum(r["no_answer_ok"] for r in neg) / len(neg), 3)
        if neg
        else None,
        "latency_avg_sec": round(sum(secs) / len(secs), 3) if secs else None,
        "latency_max_sec": max(secs) if secs else None,
        "latency_target_met": (max(secs) <= LATENCY_TARGET_SEC) if secs else None,
        "mode": rows[0]["mode"] if rows else None,
    }
    return {"summary": summary, "rows": rows}
