"""Zabbix 호출 안전장치 (A2) — 타임아웃·짧은 캐시·single-flight·실패 격리."""

import asyncio
import threading
import time

import pytest

import zabbix_ro
from dejafix_backend import zabbix
from dejafix_backend.config import Settings

TOKEN = "test-token-not-real-0123456789"
URL = "http://zabbix.invalid/api_jsonrpc.php"
REAL_BUILD_CLIENT = zabbix.build_client  # 대역으로 바꾸기 전의 진짜 함수


def make_settings(**over) -> Settings:
    base = dict(
        zabbix_mock=False,
        zabbix_url=URL,
        zabbix_api_token=TOKEN,
        zabbix_verify_tls="",
        zabbix_timeout_sec=1.0,
        zabbix_cache_ttl_sec=5.0,
        zabbix_failure_ttl_sec=2.0,
    )
    base.update(over)
    return Settings(_env_file=None, **base)


class FakeClient:
    """zabbix_ro 클라이언트 대역. 호출 횟수·지연·오류를 조절한다."""

    calls: list[tuple[str, dict]] = []
    delay = 0.0
    error: Exception | None = None
    result = "7.0.31"
    lock = threading.Lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call(self, method, params):
        with FakeClient.lock:
            FakeClient.calls.append((method, dict(params)))
        if FakeClient.delay:
            time.sleep(FakeClient.delay)
        if FakeClient.error is not None:
            raise FakeClient.error
        return FakeClient.result


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeClient.calls = []
    FakeClient.delay = 0.0
    FakeClient.error = None
    FakeClient.result = "7.0.31"
    zabbix.reset()
    monkeypatch.setattr(zabbix, "build_client", lambda settings: FakeClient())
    now = {"t": 1000.0}
    monkeypatch.setattr(zabbix, "clock", lambda: now["t"])
    yield now
    zabbix.reset()


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- 캐시


def test_success_is_reused_for_the_ttl_then_refreshed(fake):
    settings = make_settings()

    async def scenario():
        first = await zabbix.call(settings, "apiinfo.version")
        fake["t"] += 4.9  # TTL(5초) 안
        second = await zabbix.call(settings, "apiinfo.version")
        fake["t"] += 0.2  # TTL 지남
        third = await zabbix.call(settings, "apiinfo.version")
        return first, second, third

    assert run(scenario()) == ("7.0.31",) * 3
    assert len(FakeClient.calls) == 2  # 처음 + TTL 이 지난 뒤


def test_different_params_are_cached_separately(fake):
    settings = make_settings()

    async def scenario():
        await zabbix.call(settings, "host.get", {"limit": 1})
        await zabbix.call(settings, "host.get", {"limit": 2})
        await zabbix.call(settings, "host.get", {"limit": 1})

    run(scenario())
    assert [p for _, p in FakeClient.calls] == [{"limit": 1}, {"limit": 2}]


def test_cache_does_not_mix_servers(fake):
    async def scenario():
        await zabbix.call(
            make_settings(zabbix_url="http://a.invalid/x"), "apiinfo.version"
        )
        await zabbix.call(
            make_settings(zabbix_url="http://b.invalid/x"), "apiinfo.version"
        )

    run(scenario())
    assert len(FakeClient.calls) == 2


def test_cached_value_cannot_be_changed_by_the_caller(fake):
    settings = make_settings()
    FakeClient.result = [{"hostid": "1"}]

    async def scenario():
        first = await zabbix.call(settings, "host.get")
        first[0]["hostid"] = "CHANGED"
        return await zabbix.call(settings, "host.get")

    assert run(scenario()) == [{"hostid": "1"}]


# ---------------------------------------------------------------- 실패 격리


def test_failure_raises_unavailable_is_held_briefly_and_then_retried(fake):
    settings = make_settings()
    FakeClient.error = zabbix_ro.ZabbixError(
        "Zabbix 연결 실패: host.get (ConnectError)"
    )

    async def scenario():
        with pytest.raises(zabbix.ZabbixUnavailable, match="연결 실패"):
            await zabbix.call(settings, "host.get")
        fake["t"] += 1.0  # 실패 TTL(2초) 안 — 다시 부르지 않고 같은 실패
        with pytest.raises(zabbix.ZabbixUnavailable):
            await zabbix.call(settings, "host.get")
        FakeClient.error = None  # Zabbix 복구
        fake["t"] += 1.5  # 실패 TTL 지남
        return await zabbix.call(settings, "host.get")

    assert run(scenario()) == "7.0.31"
    assert (
        len(FakeClient.calls) == 2
    )  # 실패 1번 + 복구 확인 1번 (실패 중 두 번째 호출은 붙들려 있었다)


def test_unexpected_exception_is_also_isolated_and_names_only_its_type(fake):
    settings = make_settings()
    FakeClient.error = RuntimeError(f"boom {TOKEN} {URL}")

    async def scenario():
        with pytest.raises(zabbix.ZabbixUnavailable) as caught:
            await zabbix.call(settings, "host.get")
        return str(caught.value)

    message = run(scenario())
    assert "RuntimeError" in message
    assert (
        TOKEN not in message and URL not in message
    )  # 예외 내용(토큰·주소 포함 가능)은 옮기지 않는다


@pytest.mark.safety_regression
def test_write_methods_still_fail_through_the_guard(fake, monkeypatch):
    """안전장치를 거쳐도 허용 목록 밖 메서드는 진짜 zabbix_ro 가 요청 전에 거부한다 (SAFE-02)."""
    monkeypatch.setattr(zabbix, "build_client", REAL_BUILD_CLIENT)
    settings = make_settings()

    async def scenario():
        with pytest.raises(zabbix.ZabbixUnavailable, match="허용되지 않은"):
            await zabbix.call(settings, "host.update", {"hostid": "1"})

    run(scenario())


# ---------------------------------------------------------------- 타임아웃·single-flight


def test_slow_zabbix_is_cut_at_the_timeout_but_the_request_finishes_in_the_background(
    fake,
):
    settings = make_settings()
    FakeClient.delay = 0.6

    async def scenario():
        started = time.monotonic()
        with pytest.raises(zabbix.ZabbixUnavailable, match="초 안에 오지 않았습니다"):
            await zabbix.call(settings, "host.get", timeout=0.1)
        waited = time.monotonic() - started
        await asyncio.sleep(0.8)  # 뒤에서 끝나도록 기다린다
        second = await zabbix.call(
            settings, "host.get", timeout=0.1
        )  # 이미 캐시에 있다
        return waited, second

    waited, second = run(scenario())
    assert waited < 0.4  # 0.6초 걸리는 호출을 0.1초에 끊었다
    assert second == "7.0.31"
    assert len(FakeClient.calls) == 1  # 끊은 뒤에도 새로 보내지 않고 그 결과를 썼다


def test_concurrent_identical_requests_share_one_call(fake):
    settings = make_settings()
    FakeClient.delay = 0.3

    async def scenario():
        return await asyncio.gather(
            *[
                zabbix.call(settings, "problem.get", {"recent": True}, timeout=2)
                for _ in range(8)
            ]
        )

    results = run(scenario())
    assert results == ["7.0.31"] * 8
    assert len(FakeClient.calls) == 1  # 사용자 8명이 동시에 불러도 Zabbix 에는 한 번


def test_a_call_that_is_still_running_is_joined_not_repeated_after_a_timeout(fake):
    settings = make_settings()
    FakeClient.delay = 0.5

    async def scenario():
        with pytest.raises(zabbix.ZabbixUnavailable):
            await zabbix.call(settings, "host.get", timeout=0.05)
        # 아직 진행 중인 요청에 합류한다(두 번째 요청을 새로 보내지 않는다)
        return await zabbix.call(settings, "host.get", timeout=2)

    assert run(scenario()) == "7.0.31"
    assert len(FakeClient.calls) == 1


# ---------------------------------------------------------------- 목 모드


def test_mock_mode_bypasses_cache_and_timeout(monkeypatch):
    """목 모드는 즉시 답하므로 안전장치를 거치지 않는다 (진짜 zabbix_ro 목)."""
    monkeypatch.setattr(zabbix, "build_client", REAL_BUILD_CLIENT)
    settings = make_settings(zabbix_mock=True, zabbix_url="", zabbix_api_token="")

    async def scenario():
        first = await zabbix.call(settings, "apiinfo.version")
        assert zabbix._cache == {}  # 캐시에 넣지 않는다
        return first

    assert run(scenario()) == "7.0.31"
