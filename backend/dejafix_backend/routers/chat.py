"""#18 POST /api/chat  (T34) — Agent POST /v1/chat 의 SSE 를 중계한다.

계약: contracts/agent-api.md 1-2 (Backend 중계 규칙)
- 호출자는 caller="backend", 헤더 X-User-Id·X-User-Role (INTERNAL_TOKEN 이 있으면 X-Internal-Token)
- 스트림 모드(기본): 이벤트를 바꾸지 않고 그대로 넘긴다. Agent 가 연결을 거부하거나 요청 후
  CHAT_FIRST_EVENT_TIMEOUT_SEC(기본 3초) 안에 첫 이벤트(meta)가 없으면 event: error
  AGENT_UNAVAILABLE 를 보내고 닫는다. Agent 가 스트림을 열기 전에 4xx 로 거절하면 그 오류를 그대로 전달한다.
- 비스트리밍 모드(CHAT_STREAMING=false, 탈출 규칙 1): 스트림을 끝까지 읽어 JSON 하나로 합친다.
  error 이벤트가 오면 HTTP 502 + {"error": {code, message}}.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from dejafix_backend.config import Settings, get_settings
from dejafix_backend.deps import require_role
from dejafix_backend.envelope import ok
from dejafix_backend.errors import error_response

router = APIRouter(tags=["chat"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
_SSE_MEDIA_TYPE = "text/event-stream; charset=utf-8"
_UNAVAILABLE = ("AGENT_UNAVAILABLE", "Agent에 연결할 수 없습니다")


MAX_MESSAGE_CHARS = 4000
_NL = chr(10)  # 줄바꿈
_PING = ": ping" + _NL + _NL  # SSE 주석 프레임(이벤트 아님, 클라이언트가 무시)


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if (
            not value.strip()
        ):  # 공백뿐인 질문은 Agent 로 보내지 않는다 (422 VALIDATION_ERROR)
            raise ValueError("message 가 비어 있습니다")
        return value


def get_agent_transport() -> httpx.AsyncBaseTransport | None:
    """테스트에서 가짜 Agent 로 바꿔 끼우는 자리. 운영은 None(실제 네트워크)."""
    return None


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _sse_error_response(code: str, message: str) -> StreamingResponse:
    async def one() -> AsyncIterator[str]:
        yield _sse("error", {"code": code, "message": message})

    return StreamingResponse(one(), media_type=_SSE_MEDIA_TYPE, headers=_SSE_HEADERS)


def _agent_request(
    client: httpx.AsyncClient,
    body: ChatRequest,
    user: dict[str, Any],
    settings: Settings,
) -> httpx.Request:
    payload: dict[str, Any] = {
        "message": body.message,
        "context": body.context,
        "caller": "backend",
    }
    if body.conversation_id:
        payload["conversation_id"] = body.conversation_id
    headers = {"X-User-Id": str(user["id"]), "X-User-Role": user["role"]}
    if settings.internal_token:
        headers["X-Internal-Token"] = settings.internal_token
    return client.build_request("POST", "/v1/chat", json=payload, headers=headers)


async def _open(
    client: httpx.AsyncClient, request: httpx.Request
) -> tuple[httpx.Response, AsyncIterator[str], list[str]]:
    """Agent 응답 헤더와 첫 이벤트(빈 줄까지)를 읽는다."""
    response = await client.send(request, stream=True)
    lines = response.aiter_lines()
    head: list[str] = []
    if response.status_code == 200:
        async for line in lines:
            head.append(line)
            if line == "":
                break
    return response, lines, head


async def _all_lines(head: list[str], lines: AsyncIterator[str]) -> AsyncIterator[str]:
    for line in head:
        yield line
    async for line in lines:
        yield line


async def _events(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, dict]]:
    event: str | None = None
    data: list[str] = []
    async for line in lines:
        if line == "":
            if event is not None:
                yield event, json.loads("\n".join(data) or "{}")
            event, data = None, []
        elif line.startswith("event:"):
            event = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data.append(line[len("data:") :].removeprefix(" "))


async def _with_keepalive(
    lines: AsyncIterator[str], interval: float
) -> AsyncIterator[str | None]:
    """`lines` 를 그대로 내보내되, `interval` 초 동안 아무 줄도 없으면 None(틱)을 낸다.

    asyncio.wait_for 로 감싸면 시간이 지날 때 읽기 자체가 취소돼 스트림이 깨진다. 읽기 작업을 계속 두고
    기다리기만 한다. 소비자가 먼저 닫으면(브라우저가 끊김) 남은 읽기 작업을 취소한다.
    """
    iterator = lines.__aiter__()
    pending: asyncio.Future | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(iterator.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield None
                continue
            task, pending = pending, None
            try:
                line = task.result()
            except StopAsyncIteration:
                return
            yield line
    finally:
        if pending is not None:
            pending.cancel()


async def _relay(
    client: httpx.AsyncClient,
    response: httpx.Response,
    lines: AsyncIterator[str],
    head: list[str],
    keepalive_sec: float = 15.0,
) -> AsyncIterator[str]:
    """Agent 의 SSE 를 줄 단위로 그대로 넘긴다.

    Agent 가 `keepalive_sec` 초 동안 조용하면(도구 호출·LLM 대기) nginx·프록시가 유휴 연결을 끊지 않도록
    SSE 주석 프레임 `: ping` 을 보낸다. 주석 프레임은 `event:`·`data:` 가 없어 클라이언트가 무시한다(SSE 표준).
    이벤트 한가운데(event: 줄 뒤, 빈 줄 전)에서는 보내지 않는다 — 빈 줄이 그 이벤트를 끊어 버리기 때문이다.
    """
    last_event: str | None = None
    in_event = False
    broken = False
    try:
        async for line in _with_keepalive(_all_lines(head, lines), keepalive_sec):
            if line is None:
                if not in_event:
                    yield _PING
                continue
            if line.startswith("event:"):
                last_event = line[len("event:") :].strip()
            in_event = line != ""
            yield line + _NL
    except httpx.HTTPError:
        broken = True
    finally:
        await response.aclose()
        await client.aclose()
    # 스트림이 final·error 없이 끊기면 프론트가 끝까지 기다리지 않도록 오류로 닫는다
    if broken or last_event not in ("final", "error"):
        yield _sse(
            "error", {"code": _UNAVAILABLE[0], "message": "Agent 연결이 끊겼습니다"}
        )


def _new_call(call_id: str) -> dict[str, Any]:
    """비스트리밍 tool_calls[] 한 건. 계약(api.md API 18번)의 7개 키가 항상 있도록 비어 있는 값으로 채워 둔다."""
    return {
        "id": call_id,
        "tool": None,
        "args": {},
        "ok": None,
        "duration_ms": None,
        "summary": None,
        "data_clock": None,
    }


async def _collect(
    client: httpx.AsyncClient,
    response: httpx.Response,
    lines: AsyncIterator[str],
    head: list[str],
) -> JSONResponse:
    """스트림을 끝까지 읽어 비스트리밍 JSON 으로 합친다."""
    conversation_id: str | None = None
    final: dict[str, Any] | None = None
    calls: dict[str, dict[str, Any]] = {}
    try:
        async for event, data in _events(_all_lines(head, lines)):
            if event == "meta":
                conversation_id = data.get("conversation_id")
            elif event == "tool_call":
                call = calls.setdefault(data["id"], _new_call(data["id"]))
                call["tool"] = data.get("tool")
                call["args"] = data.get("args", {})
            elif event == "tool_result":
                call = calls.setdefault(data["id"], _new_call(data["id"]))
                for key in ("ok", "duration_ms", "summary", "data_clock"):
                    call[key] = data.get(key)
            elif event == "final":
                final = data
            elif event == "error":
                return error_response(
                    502, data.get("code", "AGENT_ERROR"), data.get("message", "")
                )
    except (httpx.HTTPError, ValueError, KeyError):
        return error_response(502, *_UNAVAILABLE)
    finally:
        await response.aclose()
        await client.aclose()

    if final is None:
        return error_response(502, *_UNAVAILABLE)
    return JSONResponse(
        ok(
            {
                "conversation_id": conversation_id,
                "message_id": final.get("message_id"),
                "content": final.get("content", ""),
                "evidence_ids": final.get("evidence_ids", []),
                "unknowns": final.get("unknowns", []),
                "tool_calls": list(calls.values()),
            }
        )
    )


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: dict[str, Any] = Depends(require_role("operator")),
    settings: Settings = Depends(get_settings),
    transport: httpx.AsyncBaseTransport | None = Depends(get_agent_transport),
):
    client = httpx.AsyncClient(
        base_url=settings.agent_url,
        transport=transport,
        timeout=httpx.Timeout(70.0, connect=3.0),
    )
    request = _agent_request(client, body, user, settings)
    streaming = settings.chat_streaming

    try:
        response, lines, head = await asyncio.wait_for(
            _open(client, request), timeout=settings.chat_first_event_timeout_sec
        )
    except (httpx.HTTPError, TimeoutError):
        await client.aclose()
        if streaming:
            return _sse_error_response(*_UNAVAILABLE)
        return error_response(502, *_UNAVAILABLE)

    if response.status_code >= 500:
        await response.aclose()
        await client.aclose()
        if streaming:
            return _sse_error_response(*_UNAVAILABLE)
        return error_response(502, *_UNAVAILABLE)

    if response.status_code != 200:
        # 스트림을 열기 전 Agent 오류(예: 404 CONVERSATION_NOT_FOUND, 400 BAD_REQUEST)는 그대로 전달
        raw = await response.aread()
        status = response.status_code
        await response.aclose()
        await client.aclose()
        try:
            err = json.loads(raw)["error"]
            return error_response(status, err["code"], err.get("message", ""))
        except (ValueError, KeyError, TypeError):
            return error_response(status, "AGENT_ERROR", "Agent가 요청을 거절했습니다")

    if not streaming:
        return await _collect(client, response, lines, head)
    return StreamingResponse(
        _relay(client, response, lines, head, settings.chat_keepalive_sec),
        media_type=_SSE_MEDIA_TYPE,
        headers=_SSE_HEADERS,
    )
