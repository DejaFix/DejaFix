"""CLI: python -m dejafix_kb index | search "질문" [--k 5] [--type incident_report]

설정은 환경 변수(KB_*, SHARED_DB_PATH, DOMAIN_PACK, LLM_*)에서만 읽는다. 키는 출력하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import KbSettings
from .embed import EmbedSettings, HttpEmbedder
from .indexer import run_index
from .search import search
from .store import open_kb_readonly


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dejafix_kb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index", help="수집·청킹·저장·임베딩 1회")
    sp = sub.add_parser("search", help="하이브리드 검색")
    sp.add_argument("query")
    sp.add_argument("--k", type=int, default=5)
    sp.add_argument("--type", action="append", dest="types")
    a = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    settings = KbSettings.from_env()
    if a.cmd == "index":
        print(json.dumps(run_index(settings), ensure_ascii=False))
        return 0
    es = EmbedSettings.from_env()
    embedder = HttpEmbedder(es) if es.enabled else None
    conn = open_kb_readonly(settings.path(settings.kb_db_path))
    try:
        hits, info = search(conn, a.query, a.k, embedder, a.types)
    finally:
        conn.close()
    print(
        json.dumps(
            {"info": info, "hits": [h.to_dict() for h in hits]},
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
