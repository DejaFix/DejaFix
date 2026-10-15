"""DejaFix Backend API 진입점.

저장소 루트에서: uv run --package backend uvicorn dejafix_backend.main:app --port 8000 --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dejafix_backend.config import get_settings
from dejafix_backend.db import init_backend_db
from dejafix_backend.errors import register_error_handlers
from dejafix_backend.mail import start_mail_worker, stop_mail_worker
from dejafix_backend.observability import (
    HEADER as REQUEST_ID_HEADER,
)
from dejafix_backend.observability import (
    RequestIdMiddleware,
    configure_access_log,
)
from dejafix_backend.routers import (
    auth,
    chat,
    dashboard,
    health,
    incidents,
    problems,
)
from dejafix_backend.seed import ensure_seed_users

log = logging.getLogger("dejafix.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET 환경 변수가 필요합니다 (.env.example 참고)")
    init_backend_db(settings)
    created = ensure_seed_users(settings)
    log.info("backend.db 준비 완료 (새 시드 계정: %d)", created)
    start_mail_worker(app)
    try:
        yield
    finally:
        await stop_mail_worker(app)


def create_app() -> FastAPI:
    app = FastAPI(title="DejaFix Backend API", version="0.1.0", lifespan=lifespan)
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[
            REQUEST_ID_HEADER
        ],  # 화면이 오류 보고에 요청 ID 를 읽을 수 있게
    )
    # 나중에 넣은 것이 바깥쪽: CORS preflight 응답에도 X-Request-Id 가 붙는다
    app.add_middleware(RequestIdMiddleware)
    configure_access_log()
    register_error_handlers(app)

    @app.get("/healthz", tags=["health"])
    def healthz():
        return {"status": "ok"}

    for router in (
        auth.router,
        health.router,
        dashboard.router,
        problems.router,
        incidents.router,
        chat.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
