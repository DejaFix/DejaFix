"""NFR-RAG-002 평가 도구."""

from dejafix_kb.evaluate import run_eval
from dejafix_kb.sources import SourceDoc
from dejafix_kb.store import open_kb, upsert


def test_run_eval_metrics(tmp_path):
    conn = open_kb(tmp_path / "k.db")
    upsert(
        conn,
        [
            SourceDoc(
                "runbook",
                "docs/disk.md",
                "디스크 런북",
                "# 디스크\n드라이브 용량 부족 대응 절차",
            ),
            SourceDoc(
                "runbook", "docs/cpu.md", "CPU 런북", "# CPU\n고부하 프로세스 확인 절차"
            ),
        ],
    )
    q = tmp_path / "q.yaml"
    q.write_text(
        "queries:\n"
        "  - q: 드라이브 용량 부족\n    expect: [docs/disk.md]\n"
        "  - q: 고부하 프로세스\n    expect: [docs/cpu.md]\n"
        "  - q: 고양이 사료\n    expect: []\n",
        encoding="utf-8",
    )
    result = run_eval(conn, None, q)
    s = result["summary"]
    assert (
        s["queries"] == 3 and s["recall_at_5"] == 1.0 and s["no_answer_accuracy"] == 1.0
    )
    assert 0 < s["citation_precision"] <= 1.0 and s["mode"] == "keyword"
    assert s["latency_target_met"] is True


def test_default_queries_file_has_20(tmp_path):
    import yaml

    from dejafix_kb.evaluate import DEFAULT_QUERIES

    data = yaml.safe_load(DEFAULT_QUERIES.read_text(encoding="utf-8"))
    assert len(data["queries"]) == 20
    assert any(not q["expect"] for q in data["queries"])
