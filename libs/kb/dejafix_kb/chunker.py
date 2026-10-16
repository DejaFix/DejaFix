"""청킹 규칙 (FR-RAG-003).

- 장애 리포트·팩 동작·해결 메모: 문서 1개 = 청크 1개 (요약·원인·조치·결과가 한 덩어리여야 검색 결과가 그대로 근거가 된다)
- 런북(마크다운): 제목(#) 단위로 나누고, 한 절이 MAX_TOKENS 를 넘으면 문단 단위로 다시 나누며 OVERLAP_TOKENS 만큼 겹친다
- 코드 블록(```)과 표(| 로 시작하는 줄 묶음)는 쪼개지 않는다
- 토큰 수는 글자 수 / CHARS_PER_TOKEN 으로 어림한다(한국어·영어 섞인 문서 기준 보수적으로 2)
- 청크 ID 는 kb_<해시>: 출처·순번·본문이 같으면 같은 ID (재색인해도 근거 ID 가 바뀌지 않음)
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .sources import SourceDoc

MAX_TOKENS = 500
OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 2
WHOLE_DOC_TYPES = {"incident_report", "pack_action", "resolution_note"}

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class Chunk:
    chunk_id: str
    source_type: str
    source_id: str
    title: str
    heading: str  # 런북의 절 경로 ("데모 > 리허설"), 통문서면 문서 제목
    ordinal: int
    text: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.text)


def chunk_id(source_id: str, ordinal: int, text: str) -> str:
    digest = hashlib.sha256(
        f"{source_id}\n{ordinal}\n{text}".encode("utf-8")
    ).hexdigest()
    return "kb_" + digest[:12]


def _blocks(lines: list[str]) -> list[str]:
    """문단·코드 블록·표를 쪼갤 수 없는 덩어리로 묶는다."""
    blocks: list[str] = []
    cur: list[str] = []
    in_code = False
    in_table = False

    def flush() -> None:
        if cur and any(ln.strip() for ln in cur):
            blocks.append("\n".join(cur).strip("\n"))
        cur.clear()

    for ln in lines:
        if ln.strip().startswith("```"):
            if not in_code:
                flush()
            cur.append(ln)
            in_code = not in_code
            if not in_code:
                flush()
            continue
        if in_code:
            cur.append(ln)
            continue
        is_table = ln.lstrip().startswith("|")
        if is_table != in_table:
            flush()
            in_table = is_table
        if not ln.strip() and not in_table:
            flush()
            continue
        cur.append(ln)
    flush()
    return blocks


def _sections(text: str, title: str) -> list[tuple[str, list[str]]]:
    """(절 경로, 본문 줄) 목록. 제목 줄은 경로에만 넣고 본문에도 첫 줄로 남긴다."""
    sections: list[tuple[str, list[str]]] = []
    path: list[str] = []
    body: list[str] = []
    heading = title
    for ln in text.splitlines():
        m = _HEADING.match(ln)
        if m:
            if any(b.strip() for b in body):
                sections.append((heading, body))
            level = len(m.group(1))
            path = path[: level - 1] + [m.group(2).strip()]
            heading = " > ".join(path)
            body = [ln]
            continue
        body.append(ln)
    if any(b.strip() for b in body):
        sections.append((heading, body))
    return sections


def _pack(blocks: list[str]) -> list[str]:
    """덩어리를 MAX_TOKENS 이하로 담고, 다음 청크 앞에 OVERLAP_TOKENS 만큼 이어 붙인다."""
    max_chars = MAX_TOKENS * CHARS_PER_TOKEN
    overlap_chars = OVERLAP_TOKENS * CHARS_PER_TOKEN
    pieces: list[str] = []
    cur: list[str] = []
    size = 0
    for b in blocks:
        if cur and size + len(b) > max_chars:
            pieces.append("\n\n".join(cur))
            tail = pieces[-1][-overlap_chars:]
            cur, size = [tail], len(tail)
        cur.append(b)
        size += len(b)
    if cur:
        pieces.append("\n\n".join(cur))
    return pieces


def chunk_doc(doc: SourceDoc) -> list[Chunk]:
    if doc.source_type in WHOLE_DOC_TYPES:
        return [
            Chunk(
                chunk_id(doc.source_id, 0, doc.text),
                doc.source_type,
                doc.source_id,
                doc.title,
                doc.title,
                0,
                doc.text,
                dict(doc.meta),
            )
        ]
    out: list[Chunk] = []
    for heading, body in _sections(doc.text, doc.title):
        for piece in _pack(_blocks(body)):
            n = len(out)
            out.append(
                Chunk(
                    chunk_id(doc.source_id, n, piece),
                    doc.source_type,
                    doc.source_id,
                    doc.title,
                    heading,
                    n,
                    piece,
                    dict(doc.meta),
                )
            )
    return out


def chunk_all(docs: list[SourceDoc]) -> list[Chunk]:
    return [c for d in docs for c in chunk_doc(d)]
