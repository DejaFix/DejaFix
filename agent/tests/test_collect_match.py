"""고정 수집 세트의 지표 항목 고르기: 팩 키와 가까운 순, 별칭당 최대 개수 (FR-AG-003).

Zabbix 실측(Issue #25·#34): 한 별칭에 매개변수만 다른 항목이 여러 개 걸리고(드라이브·인터페이스,
free/total), 숫자 필드는 문자열로 온다.
"""

from dejafix_agent.collect import MAX_ITEMS_PER_ALIAS, clock_iso, collect

T = "2026-10-15T01:20:00Z"


class OneShotMcp:
    def __init__(self, items):
        self.items = items

    def call(self, tool, args):
        env = {"ok": True, "collected_at": T}
        if tool == "zabbix_list_items":
            return {**env, "data": self.items}
        return {**env, "data": {}}


def _item(key, n):
    return {
        "itemid": str(n),
        "key_": key,
        "name": key,
        "lastvalue": "1",
        "lastclock": "1792027170",
    }


def test_exact_key_first_and_limit_per_alias(test_pack):
    # noise 팩 키는 probe.db[mic1]. 이름만 같은 항목 5개 + 정확한 항목 1개(맨 뒤)
    items = [_item(f"probe.db[mic{i}]", i) for i in range(2, 7)] + [
        _item("probe.db[mic1]", 1)
    ]
    calls = collect(
        {"zabbix_eventid": "1", "hostid": "10"}, OneShotMcp(items), test_pack
    )
    listed = next(c for c in calls if c.tool == "zabbix_list_items")
    noise = [i for i in listed.extra["metric_items"] if i["_alias"] == "noise"]
    assert len(noise) == MAX_ITEMS_PER_ALIAS
    assert noise[0]["key_"] == "probe.db[mic1]"  # 정확히 같은 키가 먼저


def test_string_clock_is_converted():
    # Zabbix 는 lastclock 을 문자열로 준다
    assert clock_iso("1792027170") == "2026-10-15T01:19:30Z"
    assert clock_iso("0") is None


class HistoryMcp:
    """get_history 의 data 는 객체 {itemid, source, points[], last_clock, stale} (계약 3-5)."""

    def __init__(self, points):
        self.points = points

    def call(self, tool, args):
        env = {"ok": True, "collected_at": T}
        if tool == "zabbix_get_problem":
            return {**env, "data": {"items": [{"itemid": "7", "key_": "x"}]}}
        if tool == "zabbix_get_history":
            data = {"itemid": "7", "source": "history", "points": self.points}
            return {**env, "data": data}
        return {**env, "data": {}}


def _history_summary(points, test_pack):
    calls = collect(
        {"zabbix_eventid": "1", "hostid": "10"}, HistoryMcp(points), test_pack
    )
    return next(c.summary for c in calls if c.tool == "zabbix_get_history")


def test_history_summary_counts_points(test_pack):
    pts = [{"clock": str(1792027170 + i), "value": "1"} for i in range(3)]
    assert _history_summary(pts, test_pack) == "zabbix_get_history 성공, 결과 3건"


def test_history_summary_empty_points_is_zero(test_pack):
    assert _history_summary([], test_pack) == "zabbix_get_history 성공, 결과 0건"


class TruncatedMcp:
    """항목이 많은 실제 호스트처럼 첫 목록은 잘리고(truncated) noise 항목이 빠진다(10/15 실측)."""

    def __init__(self, truncated=True):
        self.truncated = truncated
        self.searches = []

    def call(self, tool, args):
        env = {"ok": True, "collected_at": T}
        if tool == "zabbix_get_problem":
            return {**env, "data": {"items": [{"itemid": "1", "key_": "probe.temp"}]}}
        if tool == "zabbix_list_items" and "key_search" in args:
            self.searches.append(args["key_search"])
            data = [_item("probe.db[mic1]", 50), _item("probe.temp", 51)]
            return {**env, "data": data}
        if tool == "zabbix_list_items":
            data = [_item("probe.temp", 1)] + [
                _item(f"zz.other{i}", i) for i in range(5)
            ]
            return {**env, "data": data, "truncated": self.truncated}
        if tool == "zabbix_get_history":
            return {**env, "data": {"itemid": "1", "points": []}}
        return {**env, "data": {}}


def test_truncated_list_fills_missing_alias_by_key_search(test_pack):
    mcp = TruncatedMcp()
    calls = collect({"zabbix_eventid": "1", "hostid": "10"}, mcp, test_pack)
    # 못 찾은 별칭(noise)만 그 키 이름으로 1번 더 조회, 찾은 별칭(heat)은 다시 부르지 않는다
    assert mcp.searches == ["probe.db"]
    assert [c.tool for c in calls] == [
        "zabbix_get_problem",
        "zabbix_get_host",
        "zabbix_list_items",
        "zabbix_list_items",
        "zabbix_get_history",
    ]
    assert [c.seq for c in calls] == [1, 2, 3, 4, 5]
    metric = calls[2].extra["metric_items"]
    assert {(i["_alias"], i["key_"]) for i in metric} == {
        ("heat", "probe.temp"),
        ("noise", "probe.db[mic1]"),
    }
    # 보충 항목의 근거는 보충 조회, 원래 항목의 근거는 첫 목록 조회
    ev = {i["_alias"]: i["_ev"] for i in metric}
    assert ev == {"heat": calls[2].id, "noise": calls[3].id}


def test_not_truncated_makes_no_extra_call(test_pack):
    mcp = TruncatedMcp(truncated=False)
    calls = collect({"zabbix_eventid": "1", "hostid": "10"}, mcp, test_pack)
    assert mcp.searches == []
    assert [c.seq for c in calls] == [1, 2, 3, 4]


def test_fallback_fact_cites_the_extra_call(test_pack):
    from dejafix_agent.fallback import build_draft

    calls = collect({"zabbix_eventid": "1", "hostid": "10"}, TruncatedMcp(), test_pack)
    draft = build_draft({"title": "t", "host_name": "h"}, calls, test_pack)
    facts = {f["label"].split(" · ")[0]: f for f in draft["report"]["facts"]}
    assert facts["noise"]["value"] == 1.0
    assert facts["noise"]["evidence_ids"] == [calls[3].id]
    assert facts["heat"]["evidence_ids"] == [calls[2].id]
