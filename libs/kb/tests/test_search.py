"""FR-RAG-005 하이브리드 검색."""

from dejafix_kb.embed import EmbedError, normalize
from dejafix_kb.search import keyword_ranks, search
from dejafix_kb.sources import SourceDoc
from dejafix_kb.store import open_kb, upsert


class KeywordEmbedder:
    """'디스크'·'CPU' 축 2차원 가짜 임베더 — 의미 검색 흉내."""

    model = "fake"
    batch_size = 16

    def embed(self, texts):
        out = []
        for t in texts:
            disk = t.count("디스크") + t.count("드라이브") + t.count("용량")
            cpu = t.count("CPU") + t.count("부하") + t.count("프로세스")
            out.append(normalize([disk + 0.01, cpu + 0.01]))
        return out


def build(tmp_path, embed=True):
    conn = open_kb(tmp_path / "k.db")
    docs = [
        SourceDoc(
            "incident_report",
            "incident:1",
            "장애 #1 CPU",
            "# 장애 #1\n- CPU 부하 99% 원인 프로세스 과다",
            meta={"host_name": "A-PC"},
        ),
        SourceDoc(
            "incident_report",
            "incident:2",
            "장애 #2 디스크",
            "# 장애 #2\n- 디스크 드라이브 용량 부족 90% 초과",
            meta={"host_name": "B-PC"},
        ),
        SourceDoc(
            "runbook", "docs/run.md", "런북", "# 런북\n## 메일\n메일 워커 재시작 절차"
        ),
    ]
    upsert(conn, docs)
    if embed:
        from dejafix_kb.embed import embed_missing

        embed_missing(conn, KeywordEmbedder())
    return conn


def test_keyword_trigram_and_short_terms(tmp_path):
    conn = build(tmp_path, embed=False)
    ids = keyword_ranks(conn, "용량 부족")  # 2글자 단어 → LIKE 보충
    assert ids, "2글자 단어도 찾아야 한다"
    assert keyword_ranks(conn, "워커 재시작 절차")


def test_hybrid_ranks_semantic_match_first(tmp_path):
    conn = build(tmp_path)
    hits, info = search(
        conn, "저장 공간이 모자라요 드라이브", embedder=KeywordEmbedder()
    )
    assert info["mode"] == "hybrid"
    assert hits[0].source_id == "incident:2"
    assert hits[0].chunk_id.startswith("kb_")


def test_no_relevant_knowledge_returns_empty(tmp_path):
    conn = build(tmp_path, embed=False)
    hits, _ = search(conn, "zzzz qqqq")
    assert hits == []


def test_filters_type_host_and_exclude(tmp_path):
    conn = build(tmp_path)
    e = KeywordEmbedder()
    hits, _ = search(conn, "CPU 부하", embedder=e, source_types=["runbook"])
    assert all(h.source_type == "runbook" for h in hits)
    hits, _ = search(
        conn, "CPU 부하", embedder=e, host_name="B-PC", source_types=["incident_report"]
    )
    assert all(h.meta.get("host_name") == "B-PC" for h in hits)
    hits, _ = search(conn, "CPU 부하", embedder=e, exclude_source_ids=["incident:1"])
    assert "incident:1" not in {h.source_id for h in hits}


def test_embed_failure_falls_back_to_keyword(tmp_path):
    conn = build(tmp_path)

    class Broken(KeywordEmbedder):
        def embed(self, texts):
            raise EmbedError("HTTP 429")

    hits, info = search(conn, "디스크 드라이브", embedder=Broken())
    assert info == {"mode": "keyword", "embed_error": "HTTP 429"} and hits


def test_to_dict_trims_snippet(tmp_path):
    conn = build(tmp_path, embed=False)
    hits, _ = search(conn, "디스크 드라이브")
    d = hits[0].to_dict()
    assert set(d) >= {"chunk_id", "source_id", "score", "text", "meta"}


def test_like_wildcards_and_one_char_terms_do_not_match_everything(tmp_path):
    """'%'·'_'·1글자 질의가 모든 청크에 걸려 '기준 미달이면 결과 없음'을 무력화하지 않는다 (#139 리뷰 2번)."""
    conn = build(tmp_path, embed=False)
    assert keyword_ranks(conn, "%") == []
    assert keyword_ranks(conn, "_") == []
    assert keyword_ranks(conn, "a 1 #") == []
    assert keyword_ranks(conn, "%%") == []  # 2글자지만 글자 그대로 '%%' 를 찾는다
    hits, _ = search(conn, "% _ 1")
    assert hits == []
    assert keyword_ranks(conn, "9%")  # '99%' 안의 '9%' 는 글자 그대로 찾는다


def test_query_is_redacted_before_embedding(tmp_path):
    """질의의 IP·비밀값이 외부 /embeddings 로 나가지 않는다 (#139 리뷰 1번)."""
    conn = build(tmp_path)
    seen = []

    class Spy(KeywordEmbedder):
        def embed(self, texts):
            seen.extend(texts)
            return super().embed(texts)

    search(conn, "192.0.2.10 디스크 password=hunter22", embedder=Spy())
    assert seen and "192.0.2.10" not in seen[0] and "hunter22" not in seen[0]


def test_min_cosine_from_env():
    from dejafix_kb.search import MIN_COSINE, min_cosine_from_env

    assert min_cosine_from_env({}) == MIN_COSINE
    assert min_cosine_from_env({"KB_MIN_COSINE": "0.8"}) == 0.8
    assert min_cosine_from_env({"KB_MIN_COSINE": "abc"}) == MIN_COSINE
    assert min_cosine_from_env({"KB_MIN_COSINE": "5"}) == MIN_COSINE
