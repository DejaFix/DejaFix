# 로컬 연동 — 백엔드 + 프론트 같이 띄우기

compose 없이 개발 PC에서 Backend(:8000)와 Frontend 개발 서버(:5173)를 같이 띄워 실제 API로 화면을 확인하는 방법이다.
명령은 전부 **저장소 루트**에서 실행한다(프론트만 `frontend/`). 2026-10-15 PR #37(백엔드) 머지 직후 기준이다.

## 1. 순서

### ① `.env` 준비 (루트, 커밋 금지)
`.env.example`을 복사해 `.env`를 만들고 아래 값을 채운다. Claude Code는 `.env`를 읽거나 고치지 않는다(사람이 직접).

| 변수 | 로컬 값 | 비고 |
|---|---|---|
| `JWT_SECRET` | 긴 임의 문자열 | 비어 있으면 백엔드가 기동을 거부한다 |
| `DEMO_ADMIN_PASSWORD` | 직접 정함 | `admin` 계정 비밀번호. 기동 시 `backend.db`에 만든다 |
| `DEMO_ONCALL_PASSWORD` | 직접 정함 | `oncall` 계정 비밀번호 |
| `SHARED_DB_PATH` | `data/shared.db` | `.env.example` 기본값 `/data/...`은 compose용 |
| `BACKEND_DB_PATH` | `data/backend.db` | 〃 |
| `ZABBIX_MOCK` | `true` | Zabbix 없이 고정 응답 |
| `AGENT_URL` | `http://localhost:8100` | 권장. 기본값 `http://agent:8100`은 compose 안 이름이라 로컬에서는 이름 조회부터 실패한다. Agent를 띄우지 않으면 어느 쪽이든 `agent: down` |
| `MCP_ZABBIX_URL` | `http://localhost:8200/mcp` | 〃 |

- 계정 비밀번호는 `users` 행이 **처음 만들어질 때만** 쓰인다. 바꾸려면 `data/backend.db`를 지우고 다시 시드한다.

### ② 시드 (`data/*.db`)
`libs/shared_db/README.md` "시드 넣기"의 명령을 그대로 실행한다(PowerShell·Git Bash 모두 가능, `ok`가 찍히면 성공).
- `data/shared.db`(장애 6건·리포트·근거·계획)와 `data/backend.db`(메일 기록)가 생긴다. `*.db`는 커밋되지 않는다.
- 여러 번 실행해도 행이 늘지 않는다. 처음부터 다시 하려면 `data/*.db*`를 지운다.

### ③ 백엔드
```
uv run --package backend uvicorn dejafix_backend.main:app --port 8000 --reload
```
- `Application startup complete`가 보이면 준비 끝. 확인: `curl http://localhost:8000/healthz` → `{"status":"ok"}`
- API 문서: `http://localhost:8000/docs`

### ④ 프론트
```
cd frontend
npm ci            # 처음 한 번
npm run dev       # http://localhost:5173
```
- Vite가 `/api`를 `http://localhost:8000`으로 프록시한다(`frontend/vite.config.ts`, 채팅 SSE 버퍼링 끔). 브라우저 코드는 상대 경로 `/api`만 쓴다.
- **MSW(목)를 어디까지 쓸지**는 `frontend/.env.local`(또는 명령 앞 환경 변수)로 정한다. 설명은 `frontend/.env.example`.

| 하고 싶은 것 | 설정 |
|---|---|
| 백엔드 없이 전부 목 | 아무것도 안 씀(기본) |
| 전부 실제 백엔드 | `VITE_MSW=off` |
| 일부만 실제 백엔드 | `VITE_MSW_PASSTHROUGH=auth,health,incidents` (묶음: `auth` `health` `dashboard` `problems` `incidents` `chat`, `all`) |

- 다른 묶음을 통과시키면 `auth`는 자동으로 같이 통과한다(실제 백엔드는 목 토큰을 받지 않음). 이때 목으로 남은 API는 실제 JWT의 역할로 응답한다.
- 설정을 바꾸면 `npm run dev`를 다시 띄운다(Vite는 시작할 때 값을 읽는다).
- 목 ↔ 실제를 바꾸면 이전 토큰이 맞지 않아 401 → 로그인 화면으로 간다. 다시 로그인하면 된다.

## 2. 계정

| 계정 | 역할 | 실제 백엔드 비밀번호 | MSW(목) 비밀번호 |
|---|---|---|---|
| `admin` | admin | `.env` `DEMO_ADMIN_PASSWORD` | `dejafix` |
| `oncall` | operator | `.env` `DEMO_ONCALL_PASSWORD` | `dejafix` |
| `viewer` | viewer | **없음** — 백엔드는 viewer를 시드하지 않는다 | `dejafix` |

- viewer 권한(채팅 403 등)은 지금 MSW에서만 확인할 수 있다.

## 3. 시드 장애 6건 — 화면에서 보일 상태

`GET /api/incidents`는 `started_at` 내림차순이라 목록 순서는 3 → 1 → 4 → 5 → 2 → 6이다. 시각은 KST로 바꿔 보인다.

| id | 심각도 | 호스트 | 장애 | 장애 상태 | 분석 상태(`analysis.status`) | 장애 상세(`/incidents/:id`)에서 보일 것 |
|---|---|---|---|---|---|---|
| 1 | High(4) | LAB-PC-07 | High CPU utilization | 진행 중 | `done` | LLM 리포트: 원인 2개(2순위는 근거 없음 → 확신도 low), facts에 STALE 값(→ `UnknownValue`), 확인할 수 없음 NOT_COLLECTED 2건, 근거 4건, 계획 A·B·C 3단계(`max_tier` C, `mode: preview`), 메일 `sent` 1회 |
| 2 | Average(3) | LAB-PC-08 | High memory utilization | 진행 중 | `fallback` | "LLM 미연결/실패 — 규칙 기반 최소 리포트" 라벨, `impact.user_impact: null`, 실패한 근거(`ok: false`) 포함 4건, 계획 A 1단계, 메일 `failed`·시도 3회 |
| 3 | High(4) | LAB-PC-07 | Disk space is low | 진행 중 | `pending` | 리포트 없음: `report: null, evidence: [], plan: null, steps: [], mail_logs: []` → "아직 분석 전" 표시 |
| 4 | Information(1) | LAB-PC-09 | Zabbix agent version changed | 진행 중 | `skipped` | 분석 기준(`ANALYZE_MIN_SEVERITY=2`) 미만 → 분석 안 함 표시, 나머지 비어 있음 |
| 5 | High(4) | LAB-PC-08 | High CPU utilization | **해결됨** | `running` | 해결됐지만 분석이 아직 진행 중. 리포트 없음 |
| 6 | Warning(2) | LAB-PC-09 | Interface Ethernet: High bandwidth usage | 진행 중 | `failed` | 분석 실패, 리포트 없음 |

- 없는 id(예: `/incidents/99`)는 404 `NOT_FOUND`.
- 현황 홈 목록·KPI는 #10·#5를 쓴다. 단, **#5 `/api/dashboard/summary`와 #6 `/api/problems`는 아직 백엔드의 임시 응답**(고정 예시 JSON, T32 전)이라 시드와 숫자가 맞지 않는다(예: #6의 `incident_id: 12`는 시드에 없는 장애).

## 4. 지금 상태 (2026-10-15)

| API | 연결 | 비고 |
|---|---|---|
| #1 로그인·#3 me | 실제 | `admin`·`oncall`. 응답 `meta.expires_at`(8시간) |
| #4 health | 실제 | Agent·MCP를 안 띄우면 `agent: down`, `mcp_zabbix: down`. `zabbix`는 `ZABBIX_MOCK=true`면 `ok` |
| #10·#11 incidents | 실제 | 시드 6건, 커서 `meta.next_cursor` |
| #5 summary·#6 problems | 임시 응답 | 형식은 계약과 같고 값은 고정 예시 |
| #18 chat | 실제(Agent 없음) | Agent가 없으면 SSE `error` 이벤트 `AGENT_UNAVAILABLE` → 어시스턴트 패널에 "Agent 연결 안 됨" |

- **화면 대부분이 아직 `frontend/src/lib/api.ts`(Legacy 목)를 쓴다.** 그래서 MSW를 꺼도 현황 홈·장애 상세에는 실데이터가 보이지 않는다(장애 상세는 "장애를 찾을 수 없습니다"). 실제 백엔드를 쓰는 화면은 로그인과 AI 어시스턴트 패널뿐이다. 화면 이전은 to-frontend Issue에서 진행한다.
- 실데이터를 직접 보려면 개발자 도구 콘솔에서: `const { apiRequest } = await import('/src/lib/http.ts'); await apiRequest('/api/incidents/1')`

## 5. 자주 막히는 것
| 증상 | 원인·해결 |
|---|---|
| 백엔드가 `JWT_SECRET 환경 변수가 필요합니다`로 멈춤 | 루트 `.env`에 `JWT_SECRET` 없음 |
| 로그인 401 `INVALID_CREDENTIALS` | 목 비밀번호 `dejafix`를 실제 백엔드에 넣음, 또는 `backend.db`가 예전 비밀번호로 만들어짐(지우고 다시 시드) |
| `shared_db: waiting` | `SHARED_DB_PATH`가 가리키는 파일이 없음 → 시드부터 |
| 프론트 `/api/*` 502·`ECONNREFUSED` (Vite 터미널) | 백엔드가 8000에서 안 떠 있음 |
| curl로 채팅을 보내면 400 `There was an error parsing the body` | Windows 콘솔이 한글 본문을 UTF-8이 아닌 인코딩으로 보냄. 브라우저에서는 문제없다. curl은 영문으로 시험 |
