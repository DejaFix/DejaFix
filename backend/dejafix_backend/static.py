"""frontend 정적 파일(Vite dist)을 backend 가 직접 서빙한다 (dejafix-app 합본 이미지용).

FRONTEND_DIST 가 비어 있거나 index.html 이 없으면 아무것도 하지 않는다(로컬 개발·기존 compose 는 그대로).
/api/* 는 절대 index.html 로 떨어지지 않는다(없는 API 경로는 404 JSON). 그 밖의 경로는 SPA 폴백(FR-FE-016).
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

log = logging.getLogger("dejafix.backend")


def mount_frontend(app: FastAPI, dist_dir: str) -> bool:
    if not dist_dir:
        return False
    dist = Path(dist_dir).resolve()
    index = dist / "index.html"
    if not index.is_file():
        log.warning(
            "FRONTEND_DIST=%s 에 index.html 이 없어 정적 서빙을 켜지 않습니다", dist
        )
        return False
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(index)

    log.info("frontend 정적 서빙 켬: %s", dist)
    return True
