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
MAX_ITEMS_PER_ALIAS = 3


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


def _result_count(data: Any) -> int:
    """요약에 쓰는 결과 건수. 목록은 길이, 이력 객체({points: [...]})는 점 개수,
    그 밖의 단건 객체는 1 (contracts/mcp-tools.md 3-5: get_history data 는 객체)."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get("points"), list):
        return len(data["points"])
    return 1 if data else 0


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
        summary = f"{tool} 성공, 결과 {_result_count(data)}건"
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


def _rank(pack: Pack, call: ToolCall) -> list[tuple[int, dict[str, Any]]]:
    """호출 결과의 항목 중 팩 지표에 걸리는 것 → (일치 등급, 항목+별칭+근거 ID)."""
    ranked = []
    for item in _items_of(call.result.get("data")) if call.ok else []:
        found = pack.match_key(str(item.get("key_", "")))
        if found:
            ranked.append((found[1], {**item, "_alias": found[0], "_ev": call.id}))
    return ranked


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
    seq = 4
    ranked = _rank(pack, items)
    # 항목이 많은 호스트는 목록이 잘려(truncated) 이름순 뒤쪽 지표가 빠진다. 팩 별칭 중 못 찾은 것만
    # 그 별칭의 첫 키 이름으로 한 번씩 더 조회한다(별칭 수만큼이 상한, 키는 팩에서만 읽음).
    if items.ok and items.result.get("truncated"):
        found_aliases = {item["_alias"] for _, item in ranked}
        for alias, keys in pack.metrics.items():
            if alias in found_aliases or not keys:
                continue
            extra = _call(
                client,
                seq,
                "zabbix_list_items",
                {"hostid": hostid, "key_search": keys[0].split("[", 1)[0]},
            )
            seq += 1
            calls.append(extra)
            ranked += [r for r in _rank(pack, extra) if r[1]["_alias"] == alias]
    # 한 별칭에 여러 항목이 걸리면(드라이브·인터페이스별, free/total 등) 팩 키와 가까운 순으로
    # 별칭당 MAX_ITEMS_PER_ALIAS 개만 쓴다. 리포트 사실 목록이 길어지지 않게.
    ranked.sort(key=lambda r: r[0])
    per_alias: dict[str, int] = {}
    matched = []
    for _, item in ranked:
        n = per_alias.get(item["_alias"], 0)
        if n < MAX_ITEMS_PER_ALIAS:
            matched.append(item)
            per_alias[item["_alias"]] = n + 1
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
            seq,
            "zabbix_get_history",
            {"itemid": str(trigger_itemid), "time_from": iso(now - timedelta(hours=1))},
        )
        calls.append(history)
    return calls
