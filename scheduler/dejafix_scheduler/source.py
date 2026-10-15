"""Zabbix 조회 출처. Scheduler 가 부르는 메서드는 problem.get·trigger.get 두 개뿐이다.

- MockSource : ZABBIX_MOCK=true. fixture JSON 으로 동작 (FR-SCH-005)
- ZabbixRoSource : 실서버. 반드시 libs/zabbix_ro 경유 (SAFE-02, 직접 HTTP 금지)

libs/zabbix_ro(T30)에 기대하는 최소 인터페이스:
    zabbix_ro.from_env() -> client,  client.call(method: str, params: dict) -> Zabbix result
아직 없으면 SourceUnavailable 을 던지고, 폴링은 그 주기를 error 로 기록하고 다음 주기에 다시 시도한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class SourceUnavailable(RuntimeError):
    """조회 출처를 쓸 수 없음 (클라이언트 미구현·설정 누락·연결 실패)."""


class ProblemSource(Protocol):
    def problems(self) -> list[dict[str, Any]]:
        """problem.get(recent=true, selectTags) 결과. 해결된 지 얼마 안 된 Problem 도 포함."""

    def trigger_hosts(self, triggerids: list[str]) -> dict[str, dict[str, str]]:
        """{triggerid: {"hostid": str, "name": str}} — trigger.get(selectHosts) 로 호스트 보강."""


class MockSource:
    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def from_file(cls, path: Path) -> MockSource:
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def problems(self) -> list[dict[str, Any]]:
        return list(self.data.get("problems", []))

    def trigger_hosts(self, triggerids: list[str]) -> dict[str, dict[str, str]]:
        triggers = self.data.get("triggers", {})
        return {t: triggers[t] for t in triggerids if t in triggers}


class ZabbixRoSource:
    def __init__(self, client: Any):
        self.client = client

    @classmethod
    def from_env(cls) -> ZabbixRoSource:
        try:
            import zabbix_ro
        except ImportError as exc:  # pragma: no cover - 워크스페이스 멤버라 보통 있음
            raise SourceUnavailable("libs/zabbix_ro 를 불러올 수 없음") from exc
        factory = getattr(zabbix_ro, "from_env", None)
        if factory is None:
            raise SourceUnavailable("libs/zabbix_ro 클라이언트 미구현 (T30)")
        try:
            return cls(factory())
        except (
            Exception
        ) as exc:  # 설정 누락 등 — 기동은 계속하고 매 주기 error 로 남긴다
            raise SourceUnavailable(
                f"libs/zabbix_ro 클라이언트를 만들 수 없음: {type(exc).__name__}"
            ) from exc

    def problems(self) -> list[dict[str, Any]]:
        result = self.client.call(
            "problem.get",
            {
                "output": "extend",
                "recent": True,
                "selectTags": "extend",
                "sortfield": ["eventid"],
                "sortorder": "DESC",
            },
        )
        return list(result or [])

    def trigger_hosts(self, triggerids: list[str]) -> dict[str, dict[str, str]]:
        if not triggerids:
            return {}
        result = self.client.call(
            "trigger.get",
            {
                "triggerids": triggerids,
                "output": ["triggerid"],
                "selectHosts": ["hostid", "host", "name"],
            },
        )
        out: dict[str, dict[str, str]] = {}
        for trig in result or []:
            hosts = trig.get("hosts") or []
            if hosts:
                h = hosts[0]
                out[str(trig["triggerid"])] = {
                    "hostid": str(h.get("hostid")),
                    "name": str(h.get("name") or h.get("host") or ""),
                }
        return out


class UnavailableSource:
    """실서버 출처를 만들 수 없을 때. 매 주기 같은 사유로 error 를 남긴다(프로세스는 살아 있음)."""

    def __init__(self, reason: str):
        self.reason = reason

    def problems(self) -> list[dict[str, Any]]:
        raise SourceUnavailable(self.reason)

    def trigger_hosts(self, triggerids: list[str]) -> dict[str, dict[str, str]]:
        raise SourceUnavailable(self.reason)


def make_source(zabbix_mock: bool, mock_file: Path) -> ProblemSource:
    if zabbix_mock:
        return MockSource.from_file(mock_file)
    try:
        return ZabbixRoSource.from_env()
    except SourceUnavailable as exc:
        return UnavailableSource(str(exc))
