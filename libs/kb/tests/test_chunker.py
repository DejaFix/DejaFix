"""FR-RAG-003 청킹 규칙."""

from dejafix_kb import chunker
from dejafix_kb.chunker import MAX_TOKENS, chunk_all, chunk_doc, estimate_tokens
from dejafix_kb.sources import SourceDoc, collect


def doc(text, source_type="runbook", source_id="docs/x.md", title="X"):
    return SourceDoc(source_type, source_id, title, text)


def test_whole_doc_types_are_one_chunk():
    d = doc("# 장애 #1\n- 원인\n\n- 계획", "incident_report", "incident:1", "장애 #1")
    chunks = chunk_doc(d)
    assert len(chunks) == 1 and chunks[0].text == d.text
    assert chunks[0].chunk_id.startswith("kb_")


def test_runbook_split_by_heading_with_path():
    text = "# 데모\n소개\n\n## 리허설\n측정\n\n### 합격선\n3분\n\n## 실패 시\n목 모드"
    chunks = chunk_doc(doc(text))
    headings = [c.heading for c in chunks]
    assert headings == [
        "데모",
        "데모 > 리허설",
        "데모 > 리허설 > 합격선",
        "데모 > 실패 시",
    ]
    assert chunks[1].text.startswith("## 리허설")


def test_long_section_is_packed_with_overlap():
    para = "가" * 400
    text = "# 긴 절\n" + "\n\n".join(f"{i}{para}" for i in range(6))
    chunks = chunk_doc(doc(text))
    assert len(chunks) > 1
    assert all(c.tokens <= MAX_TOKENS + chunker.OVERLAP_TOKENS for c in chunks)
    tail = chunks[0].text[-chunker.OVERLAP_TOKENS * chunker.CHARS_PER_TOKEN :]
    assert chunks[1].text.startswith(tail)


def test_code_block_and_table_not_split():
    code = "```\n" + "\n\n".join(["x = 1"] * 3) + "\n```"
    table = "| a | b |\n|---|---|\n| 1 | 2 |"
    chunks = chunk_doc(doc(f"# 절\n앞\n\n{code}\n\n{table}\n\n뒤"))
    joined = "\n\n".join(c.text for c in chunks)
    assert code in joined and table in joined


def test_chunk_id_is_stable_and_unique():
    d = doc("# a\n1\n\n# b\n2")
    first = [c.chunk_id for c in chunk_doc(d)]
    assert first == [c.chunk_id for c in chunk_doc(d)]
    assert len(set(first)) == len(first)


def test_estimate_tokens():
    assert estimate_tokens("") == 1 and estimate_tokens("가나다라") == 2


def test_chunk_all_real_sources(settings):
    chunks = chunk_all(collect(settings))
    assert chunks
    assert {c.source_type for c in chunks} >= {
        "incident_report",
        "runbook",
        "pack_action",
    }
    assert len({c.chunk_id for c in chunks}) == len(chunks)
