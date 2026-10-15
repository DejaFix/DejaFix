"""SAFE-08·09·11 출력 검증 (FR-AG-005)."""

import copy

import pytest

from dejafix_agent.validate import DraftInvalid, Evidence, draft_schema, validate_draft

EV = {
    "ev_a1": Evidence(),
    "ev_a2": Evidence(),
    "ev_old": Evidence(stale=True),
    "ev_bad": Evidence(ok=False),
}


def make_draft():
    return {
        "report": {
            "summary": "CPU 사용률이 높습니다.",
            "impact": {
                "hosts": ["h1"],
                "services": [],
                "user_impact": None,
                "evidence_ids": ["ev_a1", "ev_zz"],
            },
            "causes": [
                {
                    "rank": 1,
                    "title": "c1",
                    "confidence": "medium",
                    "reasoning": "r",
                    "evidence_ids": ["ev_a1"],
                    "verify": "v",
                },
            ],
            "facts": [
                {
                    "label": "CPU",
                    "value": 96.1,
                    "unit": "%",
                    "unknown_reason": None,
                    "evidence_ids": ["ev_a1"],
                    "collected_at": None,
                },
            ],
            "unknowns": [],
            "next_checks": [],
        },
        "plan": {
            "title": "p",
            "goal": None,
            "assumptions": [],
            "steps": [
                {
                    "action_id": "t_look",
                    "title": "s",
                    "tier": "A",
                    "evidence_ids": ["ev_zz"],
                }
            ],
        },
    }


def test_schema_comes_from_contract():
    assert draft_schema()["$id"] == "dejafix/agent/analysis-draft-v0"


def test_valid_draft_keeps_supported_value():
    report, plan = validate_draft(make_draft(), EV)
    assert report["facts"][0]["value"] == 96.1
    assert report["impact"]["evidence_ids"] == ["ev_a1"]  # 없는 ev_zz 제거
    assert "tier" not in plan["steps"][0] and plan["steps"][0]["evidence_ids"] == []


def test_value_without_evidence_becomes_null():
    d = make_draft()
    d["report"]["facts"][0].update(value=93.4, evidence_ids=[])
    fact = validate_draft(d, EV)[0]["facts"][0]
    assert fact["value"] is None and fact["unknown_reason"] == "NOT_COLLECTED"


def test_fake_evidence_id_becomes_null():
    d = make_draft()
    d["report"]["facts"][0]["evidence_ids"] = ["ev_zz"]
    fact = validate_draft(d, EV)[0]["facts"][0]
    assert fact["value"] is None and fact["evidence_ids"] == []


def test_stale_and_failed_evidence():
    d = make_draft()
    d["report"]["facts"] = [
        dict(d["report"]["facts"][0], evidence_ids=["ev_old"]),
        dict(d["report"]["facts"][0], evidence_ids=["ev_bad"]),
    ]
    facts = validate_draft(d, EV)[0]["facts"]
    assert [f["unknown_reason"] for f in facts] == ["STALE", "TOOL_ERROR"]
    assert all(f["value"] is None for f in facts)


def test_causes_cut_to_three_and_unsupported_low():
    d = make_draft()
    base = d["report"]["causes"][0]
    d["report"]["causes"] = [
        dict(
            base,
            rank=r,
            title=f"c{r}",
            confidence="high",
            evidence_ids=["ev_zz"] if r == 2 else ["ev_a1"],
        )
        for r in (5, 2, 1, 4, 3)
    ]
    causes = validate_draft(d, EV)[0]["causes"]
    assert [c["title"] for c in causes] == ["c1", "c2", "c3"]
    assert [c["rank"] for c in causes] == [1, 2, 3]
    assert causes[1]["confidence"] == "low"  # 근거가 빈 원인


@pytest.mark.parametrize("bad", ["87%", "0.87", "very high"])
def test_confidence_must_be_three_levels(bad):
    d = make_draft()
    d["report"]["causes"][0]["confidence"] = bad
    with pytest.raises(DraftInvalid):
        validate_draft(d, EV)


def test_execute_field_rejected():
    d = make_draft()
    d["plan"]["steps"][0]["execute"] = True
    with pytest.raises(DraftInvalid):
        validate_draft(d, EV)


def test_input_not_mutated():
    d = make_draft()
    snapshot = copy.deepcopy(d)
    validate_draft(d, EV)
    assert d == snapshot
