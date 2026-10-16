"""Zabbix 호출 안전장치 — Backend 의 모든 Zabbix 조회(health·API 5번·API 6번)가 이 모듈을 거친다.

화면이 15초마다 부르는 API 가 느려진 Zabbix 때문에 함께 멈추지 않게 한다.
- **타임아웃**: 호출마다 `timeout` 초 안에 답이 없으면 `ZabbixUnavailable`. 이미 나간 요청은 취소하지 않고 끝까지 둔다(아래 single-flight).
- **짧은 캐시**: 성공은 `zabbix_cache_ttl_sec`(기본 5초), 실패는 `zabbix_failure_ttl_sec`(기본 2초) 동안 같은 답을 돌려줘
  사용자 여럿이 15초마다 불러도 Zabbix 에는 가볍게 간다. 실패를 오래 붙들지 않아 복구는 금방 보인다.
- **single-flight**: 같은 요청이 진행 중이면 새로 보내지 않고 그 결과를 함께 기다린다. 느린 Zabbix 에서 스레드·연결이 쌓이지 않는다.
- 목 모드(`ZABBIX_MOCK=true`)는 즉시 답하므로 캐시·타임아웃 없이 그대로 부른다.
- 실서버 호출은 반드시 `libs/zabbix_ro`(읽기 전용 허용 목록) 경유. 토큰·URL 은 응답·로그·오류 메시지에 쓰지 않는다.
"""

import asyncio
import copy
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

import zabbix_ro
from fastapi.concurrency import run_in_threadpool

from dejafix_backend.config import Settings

clock = time.monotonic  # 테스트에서 바꿔 끼운다


class ZabbixUnavailable(Exception):
    """Zabbix 를 쓸 수 없음(연결 실패·시간 초과·권한·응답 오류). 메시지에 토큰·URL 은 없다."""


@dataclass
class _Entry:
    expires: float
    value: Any = None
    error: str | None = None


_cache: dict[str, _Entry] = {}
_inflight: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}
_MAX_ENTRIES = 128


def reset() -> None:
    """캐시와 진행 중 기록을 비운다(테스트용)."""
    _cache.clear()
    _inflight.clear()


def build_client(settings: Settings) -> zabbix_ro.ZabbixRoClient:
    """Settings 로 읽기 전용 클라이언트를 만든다. 호출 때 오류를 던질 뿐 만들 때는 예외가 없다."""
    return zabbix_ro.from_env(
        {
            "ZABBIX_MOCK": "true" if settings.zabbix_mock else "false",
            "ZABBIX_URL": settings.zabbix_url,
            "ZABBIX_API_TOKEN": settings.zabbix_api_token,
            "ZABBIX_VERIFY_TLS": settings.zabbix_verify_tls,
            # 목 모드에서 상황을 고른다. 이 값을 모르는 zabbix_ro 버전은 무시한다.
            # 기본 demo: Scheduler·mcp-zabbix 목과 같은 장애(30001)·호스트라 목 모드 화면이 서로 어긋나지 않는다.
            "ZABBIX_MOCK_SCENARIO": settings.zabbix_mock_scenario,
        }
    )


def _key(settings: Settings, method: str, params: dict[str, Any]) -> str:
    """같은 서버·같은 요청만 같은 캐시를 쓴다. 주소·토큰은 해시로만 섞고 그대로 저장하지 않는다."""
    server = hashlib.sha256(
        f"{settings.zabbix_url}\0{settings.zabbix_api_token}".encode()
    ).hexdigest()[:16]
    body = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
    return f"{server}|{method}|{body}"


def _prune(now: float) -> None:
    if len(_cache) < _MAX_ENTRIES:
        return
    for key in [k for k, e in _cache.items() if e.expires <= now]:
        del _cache[key]
    if len(_cache) >= _MAX_ENTRIES:  # 그래도 많으면 가장 오래된 것부터
        for key in sorted(_cache, key=lambda k: _cache[k].expires)[: _MAX_ENTRIES // 2]:
            del _cache[key]


async def _fetch(
    key: str,
    settings: Settings,
    method: str,
    params: dict[str, Any],
    ttl: float,
    failure_ttl: float,
) -> _Entry:
    """Zabbix 를 한 번 부르고 결과(성공·실패)를 캐시에 넣는다. 예외를 밖으로 내지 않는다."""
    try:
        client = build_client(settings)
        with client:
            value = await run_in_threadpool(client.call, method, params)
        entry = _Entry(clock() + ttl, value=value)
    except zabbix_ro.ZabbixRoError as exc:
        entry = _Entry(clock() + failure_ttl, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 예상 못 한 오류도 화면 전체를 죽이지 않는다
        entry = _Entry(
            clock() + failure_ttl, error=f"Zabbix 호출 중 오류: {type(exc).__name__}"
        )
    _cache[key] = entry
    _inflight.pop(key, None)
    return entry


async def call(
    settings: Settings,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float | None = None,
) -> Any:
    """`method` 를 부르고 JSON-RPC result 를 돌려준다. 못 쓰면 `ZabbixUnavailable`."""
    params = dict(params or {})
    timeout = settings.zabbix_timeout_sec if timeout is None else timeout

    if settings.zabbix_mock:
        try:
            return build_client(settings).call(method, params)
        except zabbix_ro.ZabbixRoError as exc:
            raise ZabbixUnavailable(str(exc)) from exc

    key = _key(settings, method, params)
    now = clock()
    cached = _cache.get(key)
    if cached is not None and cached.expires > now:
        return _unwrap(cached)

    loop = asyncio.get_running_loop()
    running = _inflight.get(key)
    if running is not None and running[0] is loop:
        task = running[1]
    else:
        _prune(now)
        task = asyncio.ensure_future(
            _fetch(
                key,
                settings,
                method,
                params,
                settings.zabbix_cache_ttl_sec,
                settings.zabbix_failure_ttl_sec,
            )
        )
        _inflight[key] = (loop, task)

    try:
        # shield: 기다리다 지쳐도 이미 나간 요청은 끝까지 두어 캐시를 채운다(다음 호출이 바로 답을 받음)
        entry = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except TimeoutError:
        raise ZabbixUnavailable(
            f"Zabbix 응답이 {timeout:g}초 안에 오지 않았습니다"
        ) from None
    return _unwrap(entry)


def _unwrap(entry: _Entry) -> Any:
    if entry.error is not None:
        raise ZabbixUnavailable(entry.error)
    return copy.deepcopy(entry.value)  # 호출자가 고쳐도 캐시가 바뀌지 않게
