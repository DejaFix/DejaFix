"""VALIDATING 단계 출력 검증 (T53, FR-AG-005, SAFE-08·09·11).

1. LLM 초안이 contracts/agent-api.md 2-1 JSON Schema 를 통과해야 한다. 아니면 DraftInvalid
   (호출한 쪽이 fallback 경로로 간다).
2. 값이 있는 fact 는 evidence_ids 가 비어 있지 않고 전부 이 run 의 tool_calls 에 있어야 한다.
   아니면 value=null + unknown_reason. 근거 호출이 실패면 TOOL_ERROR, 오래된 값이면 STALE.
3. causes·impact·steps 의 없는 근거 ID 는 지운다. 근거가 빈 원인은 confidence=low.
4. 원인은 rank 순으로 최대 3개.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jsonschema

from shared_db import find_contract

MAX_CAUSES = 3


class DraftInvalid(ValueError):
    """LLM 초안이 계약 스키마를 통과하지 못함."""


@dataclass(frozen=True)
class Evidence:
    """검증에 필요한 근거(tool_calls) 정보."""

    ok: bool = True
    stale: bool = False


@lru_cache(maxsize=1)
def draft_schema() -> dict[str, Any]:
    """계약 문서의 스키마를 그대로 읽는다(사본을 두지 않는다)."""
    text = find_contract("agent-api.md").read_text(encoding="utf-8")
    for block in re.findall(r"```json\n(.*?)```", text, flags=re.S):
        if '"$schema"' in block:
            return json.loads(block)
    raise RuntimeError("contracts/agent-api.md 에 초안 JSON Schema 가 없음")


def check_schema(draft: Any) -> None:
    validator = jsonschema.Draft202012Validator(draft_schema())
    errors = sorted(validator.iter_errors(draft), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        where = "/".join(str(p) for p in first.path) or "(root)"
        raise DraftInvalid(f"{where}: {first.message}")


def _keep(ids: list[str], evidence: dict[str, Evidence]) -> list[str]:
    return [i for i in ids if i in evidence]


def validate_draft(
    draft: Any, evidence: dict[str, Evidence]
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """초안 → (검증된 report, plan 초안). plan 의 티어는 tiers.enforce_plan 이 정한다."""
    check_schema(draft)
    report = copy.deepcopy(draft["report"])
    plan = copy.deepcopy(draft.get("plan"))

    for fact in report["facts"]:
        ids = fact["evidence_ids"]
        kept = _keep(ids, evidence)
        if fact["value"] is None:
            fact["evidence_ids"] = kept
            if fact["unknown_reason"] is None:
                fact["unknown_reason"] = "NOT_COLLECTED"
            continue
        if not ids or len(kept) != len(ids):
            fact.update(value=None, unknown_reason="NOT_COLLECTED", evidence_ids=kept)
        elif any(not evidence[i].ok for i in kept):
            fact.update(value=None, unknown_reason="TOOL_ERROR")
        elif any(evidence[i].stale for i in kept):
            fact.update(value=None, unknown_reason="STALE")
        else:
            fact["unknown_reason"] = None

    causes = sorted(report["causes"], key=lambda c: c["rank"])[:MAX_CAUSES]
    for rank, cause in enumerate(causes, start=1):
        cause["rank"] = rank
        cause["evidence_ids"] = _keep(cause["evidence_ids"], evidence)
        if not cause["evidence_ids"]:
            cause["confidence"] = "low"
    report["causes"] = causes
    report["impact"]["evidence_ids"] = _keep(report["impact"]["evidence_ids"], evidence)

    if plan:
        for step in plan.get("steps", []):
            step["evidence_ids"] = _keep(step.get("evidence_ids") or [], evidence)
            step.pop("tier", None)  # LLM 티어는 버린다 (SAFE-06)
    return report, plan
