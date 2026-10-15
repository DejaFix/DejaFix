"""Zabbix 연결 점검 — `python -m zabbix_ro.probe` (T63 실연동 확인용, 읽기 전용).

`ZABBIX_URL`·`ZABBIX_API_TOKEN`·`ZABBIX_VERIFY_TLS`·`ZABBIX_MOCK` 를 **환경 변수에서만** 읽는다(.env 파일은 읽지 않는다).
허용 목록의 읽기 메서드를 각각 한 번씩 부르고 OK/FAIL 과 걸린 시간을 줄마다 찍는다. 하나라도 FAIL 이면 종료 코드 1.

- 토큰·URL 은 출력하지 않는다. 오류도 `ZabbixError` 메시지(토큰 없음)만 찍는다.
- 쓰기 메서드는 호출하지 않는다. `host.update` 가 **클라이언트에서** 막히는지만 확인한다(요청은 나가지 않는다).
  Zabbix 서버가 읽기 전용 계정의 쓰기를 거부하는지는 이 도구로 확인할 수 없다(T56 의 권한 오류 캡처로 한다).

예)  PowerShell:  $env:ZABBIX_URL="http://<주소>/api_jsonrpc.php"; $env:ZABBIX_API_TOKEN="<토큰>"; uv run python -m zabbix_ro.probe
"""

import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from zabbix_ro.client import ZabbixRoClient, from_env
from zabbix_ro.errors import MethodNotAllowed, ZabbixRoError

# (표시 이름, 메서드, 파라미터). 모두 결과를 1건으로 제한해 가볍게 부른다.
CHECKS: list[tuple[str, str, dict[str, Any]]] = [
    ("버전", "apiinfo.version", {}),
    ("호스트", "host.get", {"output": ["hostid", "name"], "limit": 1}),
    (
        "문제",
        "problem.get",
        {"output": ["eventid", "name", "severity"], "recent": True, "limit": 1},
    ),
    ("트리거", "trigger.get", {"output": ["triggerid", "description"], "limit": 1}),
    ("아이템", "item.get", {"output": ["itemid", "key_"], "limit": 1}),
]


def _summary(method: str, result: Any) -> str:
    if method == "apiinfo.version":
        return str(result)
    return f"{len(result)}건" if isinstance(result, list) else type(result).__name__


def run(
    env: Mapping[str, str],
    *,
    transport: httpx.BaseTransport | None = None,
    out: Callable[[str], None] = print,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """점검을 돌리고 종료 코드(0 모두 OK, 1 하나라도 FAIL)를 돌려준다."""
    client: ZabbixRoClient = from_env(env, transport=transport)
    scenario = getattr(client, "mock_scenario", None)  # 목 시나리오가 있는 버전에서만
    mode = "실서버"
    if client.mock:
        mode = f"목 시나리오 {scenario}" if scenario else "목"
    out(f"모드: {mode} · TLS 검증 {'켜짐' if client.verify_tls else '꺼짐'}")
    failed = 0

    if not client.mock and not client.configured:
        # call() 이 정확한 사유(URL·토큰 누락, TLS 값 오타)를 말해 준다
        try:
            client.call("apiinfo.version", {})
        except ZabbixRoError as exc:
            out(f"[FAIL] 설정  {exc}")
        return 1

    for label, method, params in CHECKS:
        started = clock()
        try:
            result = client.call(method, params)
        except ZabbixRoError as exc:
            failed += 1
            out(f"[FAIL] {label:<4} {method:<16} {exc}")
            continue
        elapsed_ms = int((clock() - started) * 1000)
        out(
            f"[ OK ] {label:<4} {method:<16} {_summary(method, result)}  ({elapsed_ms} ms)"
        )

    try:  # 쓰기 메서드는 요청 전에 클라이언트에서 막혀야 한다 (SAFE-02)
        client.call("host.update", {})
    except MethodNotAllowed:
        out("[ OK ] 쓰기 차단 host.update       요청 없이 클라이언트에서 거부됨")
    else:
        failed += 1
        out("[FAIL] 쓰기 차단 host.update       거부되지 않았다 — 즉시 알려 주세요")

    out(f"결과: {'모두 OK' if failed == 0 else f'FAIL {failed}건'}")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    import os

    return run(os.environ)


if __name__ == "__main__":
    sys.exit(main())
