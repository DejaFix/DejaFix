"""임베딩 (FR-RAG-004). OpenAI 호환 /embeddings 한 가지 방식만 쓴다(공급자 고유 의존 없음).

- 설정: KB_EMBED_MODEL 이 비어 있으면 임베딩을 끄고 키워드(FTS5) 검색만 한다.
  주소·키는 KB_EMBED_BASE_URL·KB_EMBED_API_KEY, 비어 있으면 LLM_BASE_URL·LLM_API_KEY 를 쓴다.
- 차원은 KB_EMBED_DIM(기본 768)으로 줄여 받는다. 저장은 L2 정규화한 float32 BLOB.
- 무료 등급 한도: 작은 배치(KB_EMBED_BATCH, 기본 16)로 보내고 배치 사이 KB_EMBED_PAUSE_SEC 만큼 쉰다.
  429·503 이면 Retry-After(없으면 지수 대기)만큼 기다렸다 다시 보낸다. 배치마다 저장해서 중간에 실패해도 진행분은 남는다.
- 키는 요청 헤더에만 쓰고 로그·예외 메시지에 넣지 않는다.
"""

from __future__ import annotations

import math
import os
import sqlite3
import time
from array import array
from dataclasses import dataclass
from typing import Callable, Protocol

import httpx

from .redact import redact

BATCH = 16
RETRY_BASE_SEC = 5.0
RETRY_MAX_SEC = 60.0


class EmbedError(Exception):
    """임베딩 실패. 메시지에 키·응답 원문을 넣지 않는다."""


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value else default
    except ValueError:
        return default


@dataclass(frozen=True)
class EmbedSettings:
    base_url: str
    api_key: str
    model: str
    dim: int
    timeout_sec: float = 30.0
    batch_size: int = BATCH
    pause_sec: float = 1.0  # 배치 사이 쉬는 시간
    max_retries: int = 4  # 429·503 재시도 횟수

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "EmbedSettings":
        e = os.environ if env is None else env
        return cls(
            base_url=e.get("KB_EMBED_BASE_URL") or e.get("LLM_BASE_URL") or "",
            api_key=e.get("KB_EMBED_API_KEY") or e.get("LLM_API_KEY") or "",
            model=e.get("KB_EMBED_MODEL") or "",
            # 768 은 임시 기본값 (TODO: 추후결정 — 결정 017 미결: 벡터 차원)
            dim=_int(e.get("KB_EMBED_DIM"), 768),
            batch_size=_int(e.get("KB_EMBED_BATCH"), BATCH),
            pause_sec=_float(e.get("KB_EMBED_PAUSE_SEC"), 1.0),
        )

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def to_blob(vec: list[float]) -> bytes:
    return array("f", vec).tobytes()


def from_blob(blob: bytes) -> list[float]:
    a = array("f")
    a.frombytes(blob)
    return a.tolist()


class HttpEmbedder:
    def __init__(
        self,
        settings: EmbedSettings,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not settings.enabled:
            raise EmbedError("임베딩 설정이 비어 있음 (KB_EMBED_MODEL·주소·키)")
        self.settings = settings
        self.model = settings.model
        self.batch_size = settings.batch_size
        self._client = client or httpx.Client(timeout=settings.timeout_sec)
        self._sleep = sleep

    def _post(self, batch: list[str]) -> httpx.Response:
        url = self.settings.base_url.rstrip("/") + "/embeddings"
        body = {"model": self.model, "input": batch, "dimensions": self.settings.dim}
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        attempt = 0
        while True:
            try:
                resp = self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                raise EmbedError(type(exc).__name__) from exc
            if (
                resp.status_code not in (429, 503)
                or attempt >= self.settings.max_retries
            ):
                return resp
            try:
                wait = float(resp.headers.get("retry-after", ""))
            except ValueError:
                wait = RETRY_BASE_SEC * (2**attempt)
            self._sleep(max(0.0, min(wait, RETRY_MAX_SEC)))  # 음수 Retry-After 방어
            attempt += 1

    def embed(self, texts: list[str]) -> list[list[float]]:
        if len(texts) > self.batch_size:
            raise EmbedError("배치 크기 초과 — embed_missing 이 나눠서 부른다")
        resp = self._post(texts)
        if resp.status_code != 200:
            raise EmbedError(f"HTTP {resp.status_code}")
        try:
            vecs = [d["embedding"] for d in resp.json()["data"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbedError("응답 형식을 읽을 수 없음") from exc
        if len(vecs) != len(texts):
            raise EmbedError("요청·응답 개수가 다름")
        return [normalize([float(v) for v in vec]) for vec in vecs]


def embed_missing(
    conn: sqlite3.Connection,
    embedder: Embedder,
    pause_sec: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """임베딩이 없거나 다른 모델로 만든 청크만 배치 단위로 채우고 배치마다 저장한다.

    중간에 실패하면 그때까지 채운 것은 남기고 EmbedError 를 올린다(다음 색인 때 나머지를 채움).
    """
    rows = conn.execute(
        "SELECT chunk_id, heading, text FROM kb_chunks "
        "WHERE embedding IS NULL OR embed_model IS NOT ? ORDER BY chunk_id",
        (embedder.model,),
    ).fetchall()
    size = max(1, int(getattr(embedder, "batch_size", BATCH)))
    done = 0
    for i in range(0, len(rows), size):
        if i and pause_sec:
            sleep(pause_sec)
        part = rows[i : i + size]
        # 외부 /embeddings 로 나가기 직전에 한 번 더 가린다 (NFR-RAG-001, 결정 017)
        vecs = embedder.embed([redact(f"{r['heading']}\n{r['text']}") for r in part])
        with conn:
            for r, v in zip(part, vecs):
                conn.execute(
                    "UPDATE kb_chunks SET embedding = ?, embed_model = ? WHERE chunk_id = ?",
                    (to_blob(v), embedder.model, r["chunk_id"]),
                )
            conn.execute(
                "INSERT OR REPLACE INTO kb_meta(key, value) VALUES ('embed_model', ?)",
                (embedder.model,),
            )
            conn.execute(
                "INSERT OR REPLACE INTO kb_meta(key, value) VALUES ('embed_dim', ?)",
                (str(len(vecs[0])),),
            )
        done += len(part)
    return done
