# dejafix-app 합본 이미지: backend(:8000, 프론트 정적 서빙 포함) · agent(:8100) · mcp-zabbix(:8200) · scheduler 를
# supervisord 한 프로세스 트리로 돌린다. 빌드 컨텍스트는 저장소 루트.
#   docker build -f infra/docker/app.Dockerfile -t dejafix-app .
# 기존 python.Dockerfile(서비스별 이미지)·frontend/Dockerfile 은 그대로 둔다(기존 5서비스 compose 용).

# 1) frontend 정적 파일 빌드 (frontend/Dockerfile 의 build 단계와 같음). 번들에 비밀값 없음(SAFE-13).
FROM node:22-alpine AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) python 4패키지 + supervisor
FROM ghcr.io/astral-sh/uv:0.9-python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app
COPY . /app
RUN uv sync --frozen --no-dev \
        --package backend --package agent --package mcp-zabbix --package scheduler \
    && uv pip install --python /app/.venv/bin/python "supervisor==4.3.0"

COPY --from=frontend /app/dist /app/frontend-dist
COPY infra/docker/supervisord.conf /etc/supervisord.conf

ENV PATH="/app/.venv/bin:$PATH" \
    FRONTEND_DIST=/app/frontend-dist \
    SHARED_DB_PATH=/data/shared.db \
    BACKEND_DB_PATH=/data/backend.db \
    AGENT_URL=http://127.0.0.1:8100 \
    MCP_ZABBIX_URL=http://127.0.0.1:8200/mcp

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=15s --start-period=20s --retries=5 \
    CMD ["python", "/app/infra/docker/app-healthcheck.py"]
CMD ["supervisord", "-n", "-c", "/etc/supervisord.conf"]
