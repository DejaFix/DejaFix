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
