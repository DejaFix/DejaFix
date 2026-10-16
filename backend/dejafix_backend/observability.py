"""접근 로그 (NFR-OBS-003 서비스 로그, 비밀값은 로그에 남기지 않음).

리허설·데모 중 "어느 요청이 느렸나, 어디서 실패했나"를 서버 로그 한 줄로 찾기 위한 것이다.
- 요청마다 내부 요청 ID 를 만들어 접근 로그 한 줄에 남긴다: `access request_id=… method=… path=… status=… ms=…`
  처리 안 된 오류(500)의 서버 오류 로그에도 같은 ID 가 있어 두 줄을 짝지어 찾을 수 있다.
- 요청 ID 는 **로그 안에서만** 쓴다. 응답 헤더로 내보내거나 CORS 로 노출하지 않는다(계약에 없는 응답 필드를 만들지 않는다).
- **남기지 않는 것**: 쿼리 문자열, `Authorization` 헤더, 요청·응답 본문(비밀번호·토큰·채팅 내용). 경로의 제어 문자는 `?` 로 바꾼다.
- uvicorn 기본 access log 는 쿼리 문자열이 든 요청 줄을 그대로 찍으므로 끄고, 이 접근 로그가 대신한다.
"""

import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_UNSAFE_PATH_CHARS = re.compile(r"[^\x21-\x7e]")

access_log = logging.getLogger("dejafix.access")


def configure_access_log() -> None:
    """접근 로그를 켠다. 루트 로거에 핸들러가 없을 때(uvicorn 기본 실행)만 자체 핸들러를 붙이고,
    쿼리 문자열을 찍는 uvicorn 의 access log 는 끈다."""
    access_log.setLevel(logging.INFO)
    if not access_log.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        access_log.addHandler(handler)
    logging.getLogger("uvicorn.access").disabled = True


class AccessLogMiddleware:
    """순수 ASGI 미들웨어 — SSE 스트림을 버퍼링하지 않는다."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status = {"code": 500}  # 응답을 시작하기 전에 예외가 나면 500 으로 남는다

        async def send_and_note_status(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note_status)
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
