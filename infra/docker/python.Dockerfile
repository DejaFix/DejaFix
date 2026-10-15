# Python 서비스 공용 이미지 (backend · agent · scheduler · mcp-zabbix). 빌드 컨텍스트는 저장소 루트.
#   docker build -f infra/docker/python.Dockerfile --build-arg PACKAGE=backend .
# 서비스 폴더(backend/·agent/ 등)는 각 파트 소유라 Dockerfile 을 그 안에 두지 않고 여기 하나로 둔다(T61).
# packs/·contracts/ 를 함께 복사한다(도메인 팩 로드, 스키마 멱등 적용). .env 는 .dockerignore 로 제외 — 값은 compose env_file 로만.
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim

ARG PACKAGE
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app
COPY . /app
RUN test -n "$PACKAGE" && uv sync --frozen --no-dev --package "$PACKAGE"

ENV PATH="/app/.venv/bin:$PATH"
# 실행 명령은 docker-compose.yml 의 command 에서 서비스마다 정한다
