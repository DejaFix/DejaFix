"""PLANNING 단계 티어 강제 (T50, FR-AG-006, SAFE-06·07). LLM을 다시 부르지 않고 코드만 실행한다.

- 티어는 활성 팩 actions.yaml 매칭으로만 정한다. LLM이 적은 tier 는 버린다.
- actions.yaml 에 없는 동작(또는 action_id 없음)은 팩의 default_tier(C).
- B 는 precheck·rollback 이 둘 다 있어야 한다. 단계에 없으면 팩 문구로 채우고,
  그래도 없으면 C 로 강등하고 rationale 에 사유를 남긴다.
"""

from __future__ import annotations

from typing import Any

from .packs import TIER_RANK, Pack

STEP_FIELDS = (
    "action_id",
    "title",
    "target",
    "command_preview",
    "precheck",
    "expected_effect",
    "risk",
    "rollback",
)


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def enforce_step(step: dict[str, Any], pack: Pack, seq: int) -> dict[str, Any]:
    out = {k: step.get(k) for k in STEP_FIELDS}
    out["seq"] = seq
    out["evidence_ids"] = list(step.get("evidence_ids") or [])
    aid = step.get("action_id")
    action = pack.actions.get(aid) if aid else None
    source = f"packs/{pack.name}/actions.yaml"

    if action is None:
        out["action_id"] = aid or None
        out["tier"] = pack.default_tier
        what = f"'{aid}'" if aid else "action_id 없음"
        out["rationale"] = (
            f"{source} 미등록 동작({what}) → {pack.default_tier} (SAFE-06)"
        )
        out["title"] = out["title"] or (aid or "미등록 동작")
        return out

    out["title"] = out["title"] or action.title
    for name in ("precheck", "rollback", "expected_effect", "risk"):
        if _blank(out[name]):
            out[name] = getattr(action, name)
    if _blank(out["command_preview"]) and action.command_preview:
        out["command_preview"] = next(iter(action.command_preview.values()))

    tier = action.tier
    rationale = f"규칙: {source} {action.id}"
    if tier == "B":
        missing = [n for n in ("precheck", "rollback") if _blank(out[n])]
        if missing:
            tier = "C"
            rationale += f" — B 인데 {'·'.join(missing)} 없음 → C 로 강등 (SAFE-07)"
    out["tier"] = tier
    out["rationale"] = rationale
    return out


def enforce_plan(
    plan: dict[str, Any] | None, pack: Pack
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """LLM(또는 fallback) 계획 초안 → (계획, 단계 목록). 단계가 없으면 (None, [])."""
    if not plan or not plan.get("steps"):
        return None, []
    steps = [enforce_step(s, pack, i) for i, s in enumerate(plan["steps"], start=1)]
    max_tier = max((s["tier"] for s in steps), key=TIER_RANK.__getitem__)
    out = {
        "title": plan.get("title") or "변경 계획",
        "goal": plan.get("goal"),
        "mode": "preview",
        "max_tier": max_tier,
        "assumptions": list(plan.get("assumptions") or []),
    }
    return out, steps
