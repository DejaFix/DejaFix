"""요청 ID(`X-Request-Id`)와 접근 로그 (NFR-OBS-002).

리허설·데모 중 "어느 요청이 느렸나, 어디서 실패했나"를 로그 한 줄로 찾기 위한 것이다.
- 모든 HTTP 응답에 `X-Request-Id` 를 붙인다(성공·오류·SSE·CORS preflight 모두). 들어온 값이 안전한 형식이면 그대로 쓴다.
- 접근 로그 한 줄: `access request_id=… method=… path=… status=… ms=…`
- **남기지 않는 것**: 쿼리 문자열, `Authorization` 헤더, 요청·응답 본문(비밀번호·토큰·채팅 내용). 경로의 제어 문자는 `?` 로 바꾼다.
"""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER = "X-Request-Id"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_UNSAFE_PATH_CHARS = re.compile(r"[^\x21-\x7e]")

access_log = logging.getLogger("dejafix.access")


def configure_access_log() -> None:
    """루트 로거에 핸들러가 없을 때(uvicorn 기본 실행)만 접근 로그용 핸들러를 붙인다."""
    access_log.setLevel(logging.INFO)
    if not access_log.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        access_log.addHandler(handler)


def _incoming_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            text = value.decode("latin-1")
            return text if _SAFE_ID.match(text) else None
    return None


class RequestIdMiddleware:
    """순수 ASGI 미들웨어 — SSE 스트림을 버퍼링하지 않는다."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_id(scope) or uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = {"code": 500}  # 응답을 시작하기 전에 예외가 나면 500 으로 남는다

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            access_log.info(
                "access request_id=%s method=%s path=%s status=%s ms=%d",
                request_id,
                scope.get("method", "-"),
                _UNSAFE_PATH_CHARS.sub("?", scope.get("path", "")),
                status["code"],
                elapsed_ms,
            )
