"""오류 형식 {"error": {"code", "message"}} 와 예외 핸들러. 스택 트레이스는 응답에 넣지 않는다."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("dejafix.backend")

_STATUS_CODES = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else code
        return error_response(exc.status_code, code, message)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        where = ".".join(str(p) for p in errors[0].get("loc", ())) if errors else ""
        return error_response(
            422, "VALIDATION_ERROR", f"요청 형식이 올바르지 않습니다: {where}"
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # 접근 로그의 request_id 와 같은 값을 남겨 두 줄을 짝지어 찾을 수 있게 한다(응답에는 넣지 않는다)
        request_id = getattr(request.state, "request_id", None)
        log.exception("unhandled error request_id=%s", request_id, exc_info=exc)
        return error_response(500, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다")
