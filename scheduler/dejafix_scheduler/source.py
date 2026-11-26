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
    def from_env(cls, env: dict[str, str] | None = None) -> ZabbixRoSource:
        try:
            import zabbix_ro
        except ImportError as exc:  # pragma: no cover - 워크스페이스 멤버라 보통 있음
            raise SourceUnavailable("libs/zabbix_ro 를 불러올 수 없음") from exc
        # 화면에서 정한 Zabbix 연결 파일이 바뀌면 다음 주기부터 새 연결을 쓴다(계약 #29, 결정 018).
        # 그 기능이 없는 zabbix_ro 면 예전처럼 from_env
        factory = getattr(zabbix_ro, "live_from_env", None) or getattr(
            zabbix_ro, "from_env", None
        )
        if factory is None:
            raise SourceUnavailable("libs/zabbix_ro 클라이언트 미구현 (T30)")
        try:
            return cls(factory(env) if env is not None else factory())
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


class CompanySources:
    """회사마다 그 회사 Zabbix 연결로 조회하는 출처 (결정 019).

    매 주기 `scopes()` 가 연결이 있는 회사와 그 회사 지금 연결 구분값(conn_id)을 준다.
    - 기본 회사: 연결 파일 칸 → 없으면 `.env`(conn_id 'env'). 목 모드면 목 출처(conn_id 'env')
    - 다른 회사: 연결 파일 칸만(없으면 폴링하지 않는다 — 다른 회사 연결로 떨어지지 않는다)
    회사마다 클라이언트(LiveClient)를 한 번 만들어 두고, 연결 파일이 바뀌면 다음 호출 때 따라간다.
    """

    def __init__(
        self,
        default_company: str,
        zabbix_mock: bool,
        mock_file: Path,
        env: dict[str, str] | None = None,
    ):
        import os

        self.default = default_company
        self.mock = zabbix_mock
        self.mock_file = mock_file
        self.env = dict(os.environ if env is None else env)
        self._sources: dict[str, ProblemSource] = {}

    def _company_env(self, company: str) -> dict[str, str]:
        return {
            **self.env,
            "DEFAULT_COMPANY_ID": self.default,
            "ZABBIX_COMPANY": company,
        }

    def scopes(self) -> list[tuple[str, str]]:
        """[(회사, conn_id)] — 지금 Zabbix 연결이 있는 회사들."""
        import zabbix_ro
        from zabbix_ro.connection import connection_path

        path = connection_path(self.env)
        companies = set(zabbix_ro.connected_companies(path, self.default))
        out: list[tuple[str, str]] = []
        for company in sorted(companies | {self.default}):
            found = zabbix_ro.resolve(self._company_env(company))
            if found is not None:
                out.append((company, found["conn_id"]))
            elif company == self.default and self.mock:
                out.append((company, zabbix_ro.ENV_CONN_ID))
        return out

    def source(self, company: str) -> ProblemSource:
        if company not in self._sources:
            if company == self.default and self.mock:
                self._sources[company] = MockSource.from_file(self.mock_file)
            else:
                try:
                    self._sources[company] = ZabbixRoSource.from_env(
                        self._company_env(company)
                    )
                except SourceUnavailable as exc:
                    return UnavailableSource(str(exc))
        return self._sources[company]

    def migration_conn_id(self) -> str:
        """019 이관 때 옛 행에 넣을 기본 회사 연결 구분값 (db-schema.sql 규칙 8)."""
        import zabbix_ro

        found = zabbix_ro.resolve(self._company_env(self.default))
        if found is not None:
            return found["conn_id"]
        return zabbix_ro.ENV_CONN_ID if self.mock else zabbix_ro.LEGACY_CONN_ID
