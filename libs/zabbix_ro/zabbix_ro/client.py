"""읽기 전용 Zabbix JSON-RPC 클라이언트 (FR-LIB-001·002·003, SAFE-02).

- 허용 목록(기획서 6-2) 밖 메서드는 네트워크 요청 **전에** MethodNotAllowed.
- 인증은 `Authorization: Bearer <ZABBIX_API_TOKEN>`. `user.login`·본문 `auth` 필드는 쓰지 않는다.
- ZABBIX_MOCK=true 면 네트워크 없이 fixture 를 돌려준다.
"""

import itertools
import os
from collections.abc import Mapping
from typing import Any

import httpx

from zabbix_ro.errors import MethodNotAllowed, ZabbixError
from zabbix_ro.mock import mock_result

ALLOWED_METHODS = frozenset(
    {
        "apiinfo.version",
        "problem.get",
        "event.get",
        "trigger.get",
        "host.get",
        "hostgroup.get",
        "hostinterface.get",
        "item.get",
        "history.get",
        "trend.get",
        "maintenance.get",
        "action.get",
        "alert.get",
    }
)

# Zabbix 는 apiinfo.version 에 인증을 붙이면 오류를 낸다
_NO_AUTH_METHODS = frozenset({"apiinfo.version"})

_TRUE = {"1", "true", "yes", "on"}
DEFAULT_TIMEOUT_SEC = 10.0


def _flag(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in _TRUE


class ZabbixRoClient:
    """`call(method, params)` 하나로 JSON-RPC `result` 를 돌려준다."""

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        *,
        verify_tls: bool = True,
        mock: bool = False,
        timeout: float = DEFAULT_TIMEOUT_SEC,
        transport: httpx.BaseTransport | None = None,
    ):
        self.url = url
        self.mock = mock
        self.verify_tls = verify_tls
        self._token = token
        self._ids = itertools.count(1)
        self._http: httpx.Client | None = None
        if not mock:
            if not url:
                raise ZabbixError("ZABBIX_URL 이 비어 있습니다 (ZABBIX_MOCK=false)")
            if not token:
                raise ZabbixError(
                    "ZABBIX_API_TOKEN 이 비어 있습니다 (ZABBIX_MOCK=false)"
                )
            self._http = httpx.Client(
                verify=verify_tls, timeout=timeout, transport=transport
            )

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if method not in ALLOWED_METHODS:
            raise MethodNotAllowed(method)  # 요청 전에 막는다 (SAFE-02)
        params = dict(params or {})
        if self.mock:
            return mock_result(method, params)
        return self._request(method, params)

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        assert self._http is not None and self.url
        headers = {"Content-Type": "application/json-rpc"}
        if method not in _NO_AUTH_METHODS:
            headers["Authorization"] = f"Bearer {self._token}"
        body = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": next(self._ids),
        }
        try:
            response = self._http.post(self.url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ZabbixError(f"Zabbix 응답 시간 초과: {method}") from exc
        except httpx.HTTPError as exc:
            raise ZabbixError(
                f"Zabbix 연결 실패: {method} ({type(exc).__name__})"
            ) from exc

        if response.status_code != 200:
            raise ZabbixError(f"Zabbix HTTP {response.status_code}: {method}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZabbixError(f"Zabbix 응답이 JSON 이 아닙니다: {method}") from exc

        if isinstance(payload, dict) and "error" in payload:
            err = payload["error"] or {}
            raise ZabbixError(
                f"Zabbix 오류: {err.get('message', '')} {err.get('data', '')}".strip(),
                code=err.get("code"),
                data=err.get("data"),
            )
        if not isinstance(payload, dict) or "result" not in payload:
            raise ZabbixError(f"Zabbix 응답에 result 가 없습니다: {method}")
        return payload["result"]

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    def __enter__(self) -> "ZabbixRoClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def from_env(
    env: Mapping[str, str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ZabbixRoClient:
    """ZABBIX_URL·ZABBIX_API_TOKEN·ZABBIX_VERIFY_TLS·ZABBIX_MOCK 로 클라이언트를 만든다.

    ZABBIX_MOCK=true 면 URL·토큰 없이도 만들어진다. 아니면 둘 다 있어야 하고, 없으면 ZabbixError.
    """
    env = os.environ if env is None else env
    return ZabbixRoClient(
        url=env.get("ZABBIX_URL") or None,
        token=env.get("ZABBIX_API_TOKEN") or None,
        verify_tls=_flag(env.get("ZABBIX_VERIFY_TLS"), default=True),
        mock=_flag(env.get("ZABBIX_MOCK"), default=False),
        transport=transport,
    )
