"""fallback 리포트·계획 (T51, FR-AG-007·023). LLM 없이 수집 사실만으로 만든다.

- 원인은 판단하지 않는다 → causes 는 비우고 unknowns 에 '원인 · NOT_COLLECTED'.
- 값은 MCP 가 준 최신값만 옮기고, 수집 실패·오래된 값은 null + 사유.
- 계획: 트리거 아이템 키를 팩 metrics.yaml 별칭으로 분류해 actions.yaml 의
  fallback_plans.<별칭> 동작으로 만든다. 분류 불가거나 목록이 없는 별칭은 A 동작만.
결과 모양은 LLM 초안과 같다(contracts/agent-api.md 2-1) → 같은 검증·티어 강제를 거친다.
"""

from __future__ import annotations

from typing import Any

from .collect import ToolCall, clock_iso
from .packs import Pack


def _num(value: Any) -> float | str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return round(number, 2)


def _by_tool(calls: list[ToolCall], tool: str) -> ToolCall | None:
    return next((c for c in calls if c.tool == tool), None)


def classify_incident(calls: list[ToolCall], pack: Pack) -> str | None:
    problem = _by_tool(calls, "zabbix_get_problem")
    for item in problem.extra.get("trigger_items", []) if problem else []:
        alias = pack.classify_key(str(item.get("key_", "")))
        if alias:
            return alias
    return None


def fallback_steps(
    alias: str | None, pack: Pack, target: str | None, evidence: list[str]
) -> list[dict]:
    ids = pack.fallback_plans.get(alias or "", [])
    if not ids:
        ids = [a.id for a in pack.actions.values() if a.tier == "A"]
    return [
        {
            "action_id": aid,
            "title": pack.actions[aid].title,
            "target": target,
            "evidence_ids": evidence,
        }
        for aid in ids
    ]


def build_draft(
    incident: dict[str, Any], calls: list[ToolCall], pack: Pack
) -> dict[str, Any]:
    host_name = (
        incident.get("host_name") or incident.get("hostid") or "호스트 확인 불가"
    )
    problem = _by_tool(calls, "zabbix_get_problem")
    host = _by_tool(calls, "zabbix_get_host")
    items = _by_tool(calls, "zabbix_list_items")

    facts: list[dict[str, Any]] = []
    matched = items.extra.get("metric_items", []) if items else []
    seen: set[str] = set()
    for item in matched:
        alias = item["_alias"]
        label = f"{alias} · {item.get('name') or item.get('key_')}"
        value = _num(item.get("lastvalue"))
        stale = bool(item.get("stale"))
        facts.append(
            {
                "label": label,
                "value": None if (stale or value is None) else value,
                "unit": item.get("units") or None,
                "unknown_reason": "STALE"
                if stale
                else ("NO_DATA" if value is None else None),
                "evidence_ids": [items.id],
                "collected_at": clock_iso(item.get("lastclock")),
            }
        )
        seen.add(alias)
    reason = "TOOL_ERROR" if (items is None or not items.ok) else "NO_DATA"
    for alias in pack.metrics:
        if alias not in seen:
            facts.append(
                {
                    "label": alias,
                    "value": None,
                    "unit": None,
                    "unknown_reason": reason,
                    "evidence_ids": [items.id] if items else [],
                    "collected_at": None,
                }
            )

    alias = classify_incident(calls, pack)
    ev_problem = [problem.id] if problem and problem.ok else []
    steps = fallback_steps(alias, pack, host_name, ev_problem)
    unknowns = [{"label": "원인", "reason": "NOT_COLLECTED"}]
    if problem is None or not problem.ok:
        unknowns.append({"label": "장애 상세", "reason": "TOOL_ERROR"})
    if host is None or not host.ok:
        unknowns.append({"label": "호스트 상태·유지보수 여부", "reason": "TOOL_ERROR"})

    return {
        "report": {
            "summary": f"{host_name}에서 장애 '{incident.get('title', '')}'이(가) 감지되었습니다. 수집된 사실만 정리했고 원인은 판단하지 않았습니다.",
            "impact": {
                "hosts": [host_name],
                "services": [],
                "user_impact": None,
                "evidence_ids": [host.id] if host and host.ok else [],
            },
            "causes": [],
            "facts": facts,
            "unknowns": unknowns,
            "next_checks": [
                s["title"] for s in steps if pack.actions[s["action_id"]].tier == "A"
            ],
        },
        "plan": {
            "title": f"{host_name} 대응 계획 (규칙 기반)",
            "goal": None,
            "assumptions": [],
            "steps": steps,
        },
    }
