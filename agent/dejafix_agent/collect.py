"""COLLECTING 단계 고정 수집 세트 (T49, FR-AG-003). LLM 판단 없이 코드가 순서대로 부른다.

1. zabbix_get_problem(eventid)            장애·트리거·관련 아이템
2. zabbix_get_host(hostid)               호스트·유지보수 여부
3. zabbix_list_items(hostid)             팩 metrics.yaml 의 지표 키만 골라 씀
4. zabbix_get_history(트리거 아이템, 1시간)

도구 응답 형식은 contracts/mcp-tools.md(작성 중)를 따른다. 그 전까지는 기획서 7-3 필드
(problem.items[].itemid·key_, item.itemid·key_·name·lastvalue·lastclock·units·stale)를 가정하고
모르는 모양이면 값을 쓰지 않는다(지어내지 않음).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from .packs import Pack
from .tools import ToolClient

MAX_RESULT_BYTES = 32 * 1024


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clock_iso(value: Any) -> str | None:
    """Zabbix clock(유닉스 초) 또는 ISO 문자열 → UTC ISO8601."""
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, str) and "T" in value:
        return value
    try:
        return iso(datetime.fromtimestamp(int(value), UTC))
    except (TypeError, ValueError, OSError):
        return None


@dataclass
class ToolCall:
    id: str
    seq: int
    tool: str
    args: dict[str, Any]
    ok: bool
    duration_ms: int
    result: dict[str, Any]
    called_at: str
    summary: str = ""
    data_clock: str | None = None
    stale: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def result_json(self) -> str:
        text = json.dumps(self.result, ensure_ascii=False, default=str)
        encoded = text.encode("utf-8")
        if len(encoded) <= MAX_RESULT_BYTES:
            return text
        return encoded[:MAX_RESULT_BYTES].decode("utf-8", errors="ignore")


def _new_ev() -> str:
    return "ev_" + uuid.uuid4().hex[:10]


def _call(client: ToolClient, seq: int, tool: str, args: dict[str, Any]) -> ToolCall:
    called_at = iso(utcnow())
    start = time.monotonic()
    try:
        result = client.call(tool, args)
    except Exception as exc:  # 도구 예외를 LLM·화면에 그대로 넘기지 않는다
        result = {"ok": False, "reason": "ZABBIX_ERROR", "message": type(exc).__name__}
    duration = int((time.monotonic() - start) * 1000)
    ok = bool(result.get("ok"))
    data = result.get("data")
    if ok:
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        summary = f"{tool} 성공, 결과 {count}건"
        if result.get("truncated"):
            summary += " (잘림)"
    else:
        summary = f"{tool} 실패: {result.get('reason', 'ZABBIX_ERROR')}"
    return ToolCall(
        id=_new_ev(),
        seq=seq,
        tool=tool,
        args=args,
        ok=ok,
        duration_ms=duration,
        result=result,
        called_at=called_at,
        summary=summary,
        data_clock=result.get("collected_at") if ok else None,
    )


def _items_of(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("items", "result"):
            if isinstance(data.get(key), list):
                return [d for d in data[key] if isinstance(d, dict)]
    return []


def collect(
    incident: dict[str, Any],
    client: ToolClient,
    pack: Pack,
    now: datetime | None = None,
) -> list[ToolCall]:
    now = now or utcnow()
    calls: list[ToolCall] = []

    problem = _call(
        client, 1, "zabbix_get_problem", {"eventid": incident["zabbix_eventid"]}
    )
    calls.append(problem)
    trigger_items = _items_of(problem.result.get("data")) if problem.ok else []
    problem.extra["trigger_items"] = trigger_items

    hostid = incident.get("hostid")
    host = _call(client, 2, "zabbix_get_host", {"hostid": hostid})
    calls.append(host)

    items = _call(client, 3, "zabbix_list_items", {"hostid": hostid})
    calls.append(items)
    matched = []
    for item in _items_of(items.result.get("data")) if items.ok else []:
        alias = pack.classify_key(str(item.get("key_", "")))
        if alias:
            matched.append({**item, "_alias": alias})
    items.extra["metric_items"] = matched
    clocks = [clock_iso(i.get("lastclock")) for i in matched]
    clocks = [c for c in clocks if c]
    if clocks:
        items.data_clock = max(clocks)
    # 오래됨은 항목마다 다르다. 호출 전체를 STALE 로 보는 건 고른 항목이 전부 오래됐을 때만.
    # 항목별 STALE 은 fallback 리포트의 fact 마다 따로 적는다.
    items.stale = bool(matched) and all(bool(i.get("stale")) for i in matched)

    trigger_itemid = next(
        (i.get("itemid") for i in trigger_items if i.get("itemid")), None
    )
    if trigger_itemid:
        history = _call(
            client,
            4,
            "zabbix_get_history",
            {"itemid": str(trigger_itemid), "time_from": iso(now - timedelta(hours=1))},
        )
        calls.append(history)
    return calls
