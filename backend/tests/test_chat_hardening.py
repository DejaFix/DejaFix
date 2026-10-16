"""채팅 중계 견고화 (F4) — 유휴 keepalive, 이벤트 한가운데에는 ping 금지, 브라우저가 먼저 닫을 때, 메시지 길이."""

import asyncio
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dejafix_backend.routers.chat import MAX_MESSAGE_CHARS, _with_keepalive

META = 'event: meta\ndata: {"conversation_id":"c_1","run_id":"r_1","message_id":1}\n\n'
FINAL = 'event: final\ndata: {"message_id":2,"content":"끝","evidence_ids":[],"unknowns":[]}\n\n'


# ---------------------------------------------------------------- 단위: _with_keepalive


async def slow_lines(items, delay, state):
    try:
        for item in items:
            await asyncio.sleep(delay)
            yield item
    finally:
        state["closed"] = True


def test_keepalive_ticks_while_idle_and_keeps_every_line_in_order():
    async def run():
        out = []
        async for item in _with_keepalive(slow_lines(["a", "b", "c"], 0.25, {}), 0.05):
            out.append(item)
        return out

    out = asyncio.run(run())
    assert [x for x in out if x is not None] == [
        "a",
        "b",
        "c",
    ]  # 줄은 하나도 빠지거나 바뀌지 않는다
    assert out.count(None) >= 6  # 줄 사이 조용한 동안 틱이 나온다


def test_no_tick_when_lines_come_fast():
    async def run():
        out = []
        async for item in _with_keepalive(slow_lines(["a", "b"], 0.0, {}), 5.0):
            out.append(item)
        return out

    assert asyncio.run(run()) == ["a", "b"]


def test_closing_early_cancels_the_pending_read():
    """브라우저가 먼저 닫으면 Agent 쪽 읽기를 붙잡고 있지 않는다."""

    async def run():
        state = {}
        gen = _with_keepalive(slow_lines(["a", "b"], 0.3, state), 0.05)
        first = None
        async for item in gen:
            if item is not None:
                first = item
                break
        await gen.aclose()
        await asyncio.sleep(0.1)
        return first, state

    first, state = asyncio.run(run())
    assert first == "a"
    assert state.get("closed") is True


# ---------------------------------------------------------------- 통합: 실제 소켓으로 느린 Agent


@pytest.fixture
def slow_agent():
    """메시지로 동작을 고르는 느린 Agent (실제 소켓 — ASGI 전송은 응답을 한꺼번에 모아 지연을 못 본다)."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            import json

            body = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            out = self.wfile
            if body["message"] == "split":  # 두 번째 이벤트(final) 도중에 쉰다
                # (첫 이벤트는 스트림이 시작되기 전에 통째로 읽히므로 두 번째를 쪼개야 중계 경로를 탄다)
                head, tail = FINAL.split("\n", 1)
                out.write(META.encode())
                out.flush()
                time.sleep(0.4)  # 이벤트 사이: ping 가능
                out.write(
                    (head + "\n").encode()
                )  # "event: final" 만 나가고 data 는 아직
                out.flush()
                time.sleep(0.7)  # 이벤트 도중: ping 금지
                out.write(tail.encode())
            else:  # 이벤트 사이에 쉰다
                out.write(META.encode())
                out.flush()
                time.sleep(0.7)
                out.write(FINAL.encode())
            out.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def chat(make_client, helpers, url, message, **env):
    client = make_client(AGENT_URL=url, **env)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    return client.post("/api/chat", headers=headers, json={"message": message})


def frames(text: str) -> list[str]:
    return [f for f in text.split("\n\n") if f]


def test_idle_agent_gets_ping_comment_frames_and_events_stay_byte_for_byte(
    make_client, helpers, slow_agent
):
    response = chat(make_client, helpers, slow_agent, "gap", CHAT_KEEPALIVE_SEC="0.15")
    assert response.status_code == 200
    text = response.text
    assert text.count(": ping\n\n") >= 2  # 0.7초 조용한 동안 여러 번
    assert (
        text.replace(": ping\n\n", "") == META + FINAL
    )  # 이벤트는 한 글자도 바뀌지 않았다
    # 모든 프레임이 주석(ping)이거나 event+data 를 가진 온전한 이벤트다
    for frame in frames(text):
        assert frame == ": ping" or (
            frame.startswith("event: ") and "\ndata: " in frame
        ), frame
    # 주석 프레임은 meta 와 final 사이에만 있다
    assert text.index(META) < text.index(": ping") < text.index(FINAL)


def test_ping_is_never_sent_in_the_middle_of_an_event(make_client, helpers, slow_agent):
    """event: 줄만 나가고 data: 가 늦으면, 그 사이의 빈 줄(ping)이 이벤트를 끊어 버린다 — 그래서 보내지 않는다."""
    response = chat(
        make_client, helpers, slow_agent, "split", CHAT_KEEPALIVE_SEC="0.15"
    )
    text = response.text
    assert (
        text.count(": ping\n\n") >= 1
    )  # 이벤트 사이에서는 ping 이 나갔다(검사가 실제로 중계 경로를 탐)
    assert "event: final\n: ping" not in text  # 이벤트 도중에는 나가지 않았다
    assert text.replace(": ping\n\n", "") == META + FINAL
    for frame in frames(text):
        assert frame == ": ping" or (
            frame.startswith("event: ") and "\ndata: " in frame
        ), frame


def test_no_ping_when_the_agent_is_quick(make_client, helpers, slow_agent):
    """기본 15초보다 빨리 끝나면 ping 은 없다 (평소 응답은 그대로)."""
    response = chat(make_client, helpers, slow_agent, "gap")  # 기본 15초
    assert response.text == META + FINAL


# ---------------------------------------------------------------- 메시지 길이


def test_message_over_the_limit_is_422_and_the_limit_itself_is_allowed(client, oncall):
    too_long = client.post(
        "/api/chat", headers=oncall, json={"message": "가" * (MAX_MESSAGE_CHARS + 1)}
    )
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "VALIDATION_ERROR"
    at_limit = client.post(
        "/api/chat", headers=oncall, json={"message": "가" * MAX_MESSAGE_CHARS}
    )
    assert at_limit.status_code == 200  # 검증은 통과 (Agent 가 없어 오류 이벤트 스트림)


@pytest.mark.parametrize("blank", ["   ", "\n\t ", " \n "])
def test_whitespace_only_message_is_422(client, oncall, blank):
    response = client.post("/api/chat", headers=oncall, json={"message": blank})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
