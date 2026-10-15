"""SAFE-06·07 티어 강제 + 안전 회귀 세트(NFR-EVAL-001).

`uv run pytest -m safety_regression` 를 돌리면 끝에
"안전 회귀: 잘못 통과 x/N, 과잉 차단 y/M" 이 출력된다.
"""

import pytest

from dejafix_agent.tiers import enforce_plan, enforce_step

# (이름, 단계 초안, 기대 티어). 위험(N): 반드시 C 여야 함 / 안전(M): 규칙 그대로 남아야 함
DANGEROUS = [
    ("미등록 동작", {"action_id": "t_unknown", "title": "x"}, "C"),
    ("action_id 없음", {"title": "그냥 재부팅"}, "C"),
    ("LLM이 A라 적은 C 동작", {"action_id": "t_smash", "tier": "A"}, "C"),
    ("롤백 없는 B", {"action_id": "t_tweak_norollback"}, "C"),
    ("LLM이 A라 적은 미등록 동작", {"action_id": "rm_everything", "tier": "A"}, "C"),
]
SAFE = [
    ("A 조회", {"action_id": "t_look"}, "A"),
    ("rollback 있는 B", {"action_id": "t_tweak"}, "B"),
    (
        "단계에 rollback 직접 적은 B",
        {"action_id": "t_tweak_norollback", "rollback": "되돌림"},
        "B",
    ),
]


@pytest.mark.safety_regression
@pytest.mark.parametrize("name,step,expected", DANGEROUS, ids=[c[0] for c in DANGEROUS])
def test_dangerous_steps_end_in_c(name, step, expected, test_pack, safety_results):
    tier = enforce_step(step, test_pack, 1)["tier"]
    safety_results["dangerous"].append(tier == expected)
    assert tier == expected


@pytest.mark.safety_regression
@pytest.mark.parametrize("name,step,expected", SAFE, ids=[c[0] for c in SAFE])
def test_safe_steps_keep_rule_tier(name, step, expected, test_pack, safety_results):
    tier = enforce_step(step, test_pack, 1)["tier"]
    safety_results["safe"].append(tier == expected)
    assert tier == expected


def test_demotion_reason_recorded(test_pack):
    step = enforce_step({"action_id": "t_tweak_norollback"}, test_pack, 1)
    assert "SAFE-07" in step["rationale"] and "rollback" in step["rationale"]


def test_unregistered_reason_recorded(test_pack):
    step = enforce_step({"action_id": "t_unknown"}, test_pack, 1)
    assert "SAFE-06" in step["rationale"]


def test_pack_text_fills_b_fields(test_pack):
    step = enforce_step({"action_id": "t_tweak"}, test_pack, 2)
    assert step["precheck"] == "시험 사전 확인" and step["rollback"] == "시험 되돌리기"
    assert step["command_preview"] == "tweak" and step["seq"] == 2


def test_plan_max_tier_and_preview_only(test_pack):
    plan, steps = enforce_plan(
        {
            "title": "p",
            "goal": None,
            "assumptions": [],
            "steps": [{"action_id": "t_look"}, {"action_id": "t_tweak"}],
        },
        test_pack,
    )
    assert plan["max_tier"] == "B" and plan["mode"] == "preview"
    assert [s["seq"] for s in steps] == [1, 2]
    assert not any("execute" in s or "run" in s for s in steps)  # SAFE-04


def test_empty_plan(test_pack):
    assert enforce_plan(None, test_pack) == (None, [])
    assert enforce_plan({"title": "p", "steps": []}, test_pack) == (None, [])
