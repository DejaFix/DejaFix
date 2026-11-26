"""DejaFix Backend API 진입점.

저장소 루트에서: uv run --package backend uvicorn dejafix_backend.main:app --port 8000 --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from dejafix_backend import company
from dejafix_backend.config import get_settings
from dejafix_backend.db import init_backend_db
from dejafix_backend.errors import register_error_handlers
from dejafix_backend.mail import start_mail_worker, stop_mail_worker
from dejafix_backend.observability import AccessLogMiddleware, configure_access_log
from dejafix_backend.routers import (
    auth,
    chat,
    dashboard,
    health,
    hosts,
    incidents,
    notes,
    problems,
    zabbix_settings,
)
from dejafix_backend.seed import ensure_seed_users
from dejafix_backend.static import mount_frontend

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
        allow_headers=["Authorization", "Content-Type", company.HEADER],
    )
    # 나중에 넣은 것이 바깥쪽: CORS preflight 요청도 접근 로그에 남는다
    app.add_middleware(AccessLogMiddleware)
    configure_access_log()
    register_error_handlers(app)

    @app.middleware("http")
    async def company_echo(request: Request, call_next):
        # 결정 019: 거른 회사를 돌려준다(AXcellent 프록시는 이 값이 요청 회사와 같을 때만 그 회사 화면에 넘긴다)
        response = await call_next(request)
        scope = getattr(request.state, "company", None)
        if scope:
            response.headers[company.ECHO] = scope
        return response

    @app.get("/healthz", tags=["health"])
    def healthz():
        return {"status": "ok"}

    for router in (
        auth.router,
        health.router,
        dashboard.router,
        problems.router,
        hosts.router,
        incidents.router,
        notes.router,
        chat.router,
        zabbix_settings.router,
    ):
        app.include_router(router, prefix="/api")
    # 반드시 라우터 등록 뒤: 마지막에 붙는 SPA 폴백이 API·/healthz 를 가리지 않게 한다
    mount_frontend(app, settings.frontend_dist)
    return app


app = create_app()
