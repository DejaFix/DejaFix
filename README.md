# DejaFix

장애 대응 코파일럿(화면 부제 "Zabbix AI"). Zabbix 알람이 뜨면 AI가 조회만으로 원인 후보와 영향 범위를 정리하고, **조치는 실행 전에 규칙으로 안전성을 판정해 계획(미리보기)으로 제시**하며, 모든 수치에 근거를 붙인다. 결과는 웹 화면과 담당자 메일로 전달한다. 실행 여부는 규칙 파일(`packs/<domain>/actions.yaml`)과 코드가 결정하고 LLM은 결정하지 않는다. 차별점 3축은 `docs/plan.md` 1-3.

6명이 각자 Claude Code로 개발한다. 규칙은 루트 `CLAUDE.md`, 금요일(10/16) 범위는 `docs/mvp-checklist.md`, 작업 순서는 `docs/work-order.md`.

## 구조

| 폴더 | 역할 | 포트 | 주담당 |
|---|---|---|---|
| `frontend/` | React + Vite + TS, nginx가 `/api`를 backend로 프록시 | 80 → 호스트 **8080**(유일한 공개 포트) | 화면 담당·연동·인프라 담당 |
| `backend/` | FastAPI BFF — 로그인·화면 API·채팅 중계·메일 워커 | 8000(내부) | Backend 담당(메일 워커는 DB·메일 담당) |
| `agent/` | 분석 워커·상태 머신·LLM 호출·리포트·계획·채팅 | 8100(내부) | 팀장 |
| `mcp-zabbix/` | Zabbix `*.get`을 MCP 도구로 노출 | 8200 `/mcp`(내부) | Zabbix·MCP 담당 |
| `scheduler/` | 30초 `problem.get` 폴링 → `incidents` | 없음 | DB·메일 담당 |
| `libs/zabbix_ro/` | 공용 읽기 전용 Zabbix 클라이언트(허용 목록 강제) | — | Backend 담당 |
| `packs/it/` | IT 도메인 팩 — `metrics.yaml`·`actions.yaml`·`prompts/` | — | 팀장 |
| `contracts/` | 파트 간 계약 5종(변경은 2인 승인 PR) | — | 각 소유자 |
| `infra/` | `docker-compose.yml`, Dockerfile, 운영 스크립트, Zabbix 설정 기록 | — | 연동·인프라 담당·Zabbix·MCP 담당 |
| `mcp-aws/` | [이후] L1 자리(README만) | 8300 예약 | 미배정 |
| `docs/` | 문서 지도는 `docs/README.md` | — | — |

호출 방향은 한 방향 **Frontend → Backend → Agent → MCP → 외부**. 데이터는 SQLite 2파일(`/data/shared.db` 쓰기 Agent·Scheduler, `/data/backend.db` Backend)을 named volume에 둔다. 운영 Zabbix는 Ubuntu VM의 외부 서비스라 compose에 없다.

## 준비 (Windows 10/11, 1회)
```powershell
winget install Git.Git Docker.DockerDesktop OpenJS.NodeJS.LTS Python.Python.3.12 astral-sh.uv
git config --global core.autocrlf false
git config --global core.longpaths true
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```
Node 22 LTS, Python 3.12, uv, npm만 쓴다(pip·poetry·pnpm·yarn 금지).

## 받기
```powershell
cd C:\Users\403\Documents
git clone https://github.com/DejaFix/DejaFix.git
cd DejaFix          # 기본 브랜치 dev
Copy-Item .env.example .env   # 값은 Slack DM으로 받은 것만 직접 입력. .env는 커밋 금지
```

## 로컬 실행 (개발 기본 — 목 모드)
`.env`에서 `ZABBIX_MOCK=true`, `MAIL_PROVIDER=console`, `LLM_FAKE=true`(테스트용, 데모 금지)로 두면 Zabbix·LLM·메일 없이 전 서비스가 뜬다.

```powershell
uv sync                                   # 루트 uv workspace (backend·agent·mcp-zabbix·scheduler·libs/zabbix_ro)
uv run --package mcp-zabbix python -m mcp_zabbix            # :8200/mcp
uv run --package agent uvicorn dejafix_agent.main:app --port 8100
uv run --package backend uvicorn dejafix_backend.main:app --port 8000
uv run --package scheduler python -m scheduler
cd frontend; npm ci; npm run dev          # :5173, /api → localhost:8000 프록시 (백엔드 없으면 MSW)
```
패키지·모듈 이름은 각 폴더 `CLAUDE.md`의 "실행" 절이 기준이다(골격 PR에서 확정). 로컬 실행은 탈출 규칙 3(compose 불안정 시 데모 대체 경로)이기도 하다.

## compose 실행 (데모·통합 테스트)
```powershell
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.yml ps        # 5개 Up, 공개 포트 8080만
docker compose -f infra/docker-compose.yml logs -f --tail=100 agent
```
`.env`를 바꾸면 `restart`가 아니라 `up -d`. 접속 `http://localhost:8080`, 데모 계정 `admin`·`oncall`(비밀번호는 `.env`).

## 품질 기준 (PR 머지 조건)
- Python: `uv run ruff check .` · `uv run ruff format --check .` · `uv run pytest` / Frontend: `npm run lint` · `npx tsc --noEmit` · `npm run build`
- 필수 안전 테스트 8종과 엔진 하드코딩 `rg` 검사는 루트 `CLAUDE.md`.

## 브랜치
`dev`(기본, 통합) ← `feat/<영역>-<주제>` · `fix/…` · `docs/…` · `night/<파트>-<MMDD>` PR(승인 1명, squash). `main`은 데모·배포 안정본(10/16 11:30 dev → main, 태그 `release/demo-1016`). 직접 push 금지.

## 문서
- `docs/mvp-checklist.md` 금요일 [필수] / `docs/work-order.md` 전체 작업 순서 / `docs/plan.md` 기획서 v1.3 / `docs/requirements.md` 요구사항정의서 v1.3 / `docs/review-v1.3.md` 검토 의견 / `docs/night/` 야간 작업 루프 / `docs/demo/` 시연
