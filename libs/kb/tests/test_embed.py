"""FR-RAG-004 임베딩 (실 API 없이 가짜 임베더·MockTransport)."""

import json
import math

import httpx
import pytest

from dejafix_kb.embed import (
    EmbedError,
    EmbedSettings,
    HttpEmbedder,
    embed_missing,
    from_blob,
    normalize,
    to_blob,
)
from dejafix_kb.indexer import run_index
from dejafix_kb.store import open_kb


class FakeEmbedder:
    model = "fake-embed"

    def __init__(self, dim=4):
        self.dim = dim
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [
            normalize([float(len(t) % 7 + 1)] + [1.0] * (self.dim - 1)) for t in texts
        ]


def test_settings_disabled_without_model():
    assert not EmbedSettings.from_env(
        {"LLM_BASE_URL": "http://x", "LLM_API_KEY": "k"}
    ).enabled
    s = EmbedSettings.from_env(
        {"LLM_BASE_URL": "http://x", "LLM_API_KEY": "k", "KB_EMBED_MODEL": "m"}
    )
    assert s.enabled and s.dim == 768


def test_blob_roundtrip_and_normalize():
    v = normalize([3.0, 4.0])
    assert math.isclose(v[0], 0.6, rel_tol=1e-6)
    assert [round(x, 5) for x in from_blob(to_blob(v))] == [0.6, 0.8]


def test_http_embedder_batches_and_hides_key():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(
            (request.headers["authorization"], body["dimensions"], len(body["input"]))
        )
        return httpx.Response(
            200, json={"data": [{"embedding": [1.0, 0.0]} for _ in body["input"]]}
        )

    s = EmbedSettings("http://e/v1", "secret-key", "m", 2)
    e = HttpEmbedder(s, httpx.Client(transport=httpx.MockTransport(handler)))
    vecs = e.embed([f"t{i}" for i in range(16)])
    assert len(vecs) == 16 and [n for *_, n in seen] == [16]
    assert seen[0][0] == "Bearer secret-key" and seen[0][1] == 2
    with pytest.raises(EmbedError):
        e.embed(["x"] * 17)  # 배치 나누기는 embed_missing 몫


def test_http_embedder_retries_429_with_retry_after():
    statuses = iter([429, 429, 200])
    waits = []

    def handler(request):
        if next(statuses) == 429:
            return httpx.Response(429, headers={"retry-after": "3"})
        return httpx.Response(200, json={"data": [{"embedding": [1.0]}]})

    s = EmbedSettings("http://e/v1", "k", "m", 1)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    e = HttpEmbedder(s, client, sleep=waits.append)
    assert e.embed(["a"]) == [[1.0]] and waits == [3.0, 3.0]


def test_embed_missing_keeps_partial_progress(settings):
    run_index(settings, embed_settings=EmbedSettings("", "", "", 768))
    conn = open_kb(settings.kb_db_path)

    class FailsSecond(FakeEmbedder):
        batch_size = 2

        batches = 0

        def embed(self, texts):
            self.batches += 1
            if self.batches == 2:
                raise EmbedError("HTTP 429")
            return super().embed(texts)

    with pytest.raises(EmbedError):
        embed_missing(conn, FailsSecond())
    filled = conn.execute(
        "select count(*) from kb_chunks where embedding is not null"
    ).fetchone()[0]
    assert filled == 2


def test_http_embedder_error_has_no_secret():
    def handler(request):
        return httpx.Response(500, text="secret-key leaked?")

    s = EmbedSettings("http://e/v1", "secret-key", "m", 2)
    e = HttpEmbedder(s, httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(EmbedError) as exc:
        e.embed(["a"])
    assert "secret-key" not in str(exc.value)


def test_embed_missing_only_new_or_other_model(tmp_path, settings):
    run_index(settings, embedder=FakeEmbedder())
    conn = open_kb(settings.kb_db_path)
    total = conn.execute("select count(*) from kb_chunks").fetchone()[0]
    assert (
        conn.execute(
            "select count(*) from kb_chunks where embedding is null"
        ).fetchone()[0]
        == 0
    )
    assert embed_missing(conn, FakeEmbedder()) == 0
    other = FakeEmbedder()
    other.model = "other"
    assert embed_missing(conn, other) == total
    assert (
        conn.execute("select value from kb_meta where key='embed_model'").fetchone()[0]
        == "other"
    )


def test_index_without_embedding_settings_is_keyword_only(settings):
    result = run_index(settings, embed_settings=EmbedSettings("", "", "", 768))
    assert result["counts"]["embedded"] == 0 and result["embed_error"] is None
    assert result["counts"]["chunks"] > 0


def test_index_embed_failure_keeps_keyword_index(settings):
    class Broken(FakeEmbedder):
        def embed(self, texts):
            raise EmbedError("HTTP 429")

    result = run_index(settings, embedder=Broken())
    assert result["embed_error"] == "HTTP 429" and result["counts"]["chunks"] > 0
