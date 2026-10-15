# backend — BFF (FastAPI :8000, 내부 전용 · 외부 공개는 frontend 8080뿐)

주담당 Backend 담당 · 부담당 연동·인프라 담당. 메일 워커(`backend/` 안)는 DB·메일 담당(부 Backend 담당).
먼저 읽을 것: 루트 `CLAUDE.md` → `docs/mvp-checklist.md` "Backend" → `contracts/api.md`·`contracts/incident.schema.json`·`contracts/agent-api.md`·`contracts/db-schema.sql`.

## 역할 ([필수]만 — API 8개 + 메일 워커)

| # | 엔드포인트 | 최소 역할 | 핵심 | 근거 |
|---|---|---|---|---|
| 1 | `POST /api/auth/login` | 공개 | `{username,password}` → `{token, user}`, 401 `INVALID_CREDENTIALS`. 시드 `admin`(admin)·`oncall`(operator)을 `.env` 비밀번호로 생성, bcrypt/argon2 | FR-BE-001 |
| 3 | `GET /api/auth/me` | 로그인 | `{id, username, role, display_name, email}` | FR-BE-002 |
| 4 | `GET /api/health` | 로그인 | `{zabbix, agent, mcp_zabbix, shared_db, backend_db, scheduler_last_ok}`. `shared.db` 없으면 500이 아니라 `shared_db:"waiting"`, 요청마다 재시도. `scheduler_last_ok`는 `scheduler_jobs.poll_problems.last_ok_at` | FR-BE-004 |
| 5 | `GET /api/dashboard/summary` | viewer | KPI 4종 전부 `Measured`. 활성 장애 = `incidents.status='problem'` 수 / High 이상 = severity ≥ 4 / 감시 호스트 = Zabbix status=0 호스트 수, 정상 = 가용성 1 + 활성 Problem 0, 확인 불가는 `hosts.unknown` / 오늘 리포트 수(KST) / 평균 분석 시간. Zabbix 끊기면 Zabbix 의존 KPI만 `unknown:true, unknown_reason:"TOOL_ERROR"` | FR-BE-005 |
| 6 | `GET /api/problems?severity_min=&hostid=` | viewer | `problem.get` + `trigger.get`, DejaFix `incident_id` 매칭(null 가능) | FR-BE-006 |
| 10 | `GET /api/incidents?status=&severity_min=&limit=&cursor=` | viewer | 표준 Incident 형식 + `analysis{status, report_id, plan_id}`. `analysis.status` 6값 `skipped/pending/running/done/fallback/failed` | FR-BE-008 |
| 11 | `GET /api/incidents/{id}` | viewer | 한 번에 `{incident, report(최신 version), evidence[tool_calls], plan, steps[], mail_logs[]}`. `causes[].evidence_ids`가 전부 `evidence[]`에 존재. 응답에 `execute`/`run` 없음, `plan.mode:"preview"` | FR-BE-009 |
| 18 | `POST /api/chat` | operator | Agent `/v1/chat` SSE를 **그대로** 중계(첫 `meta` 3초 안). 헤더 `X-User-Id`·`X-User-Role`, `caller=backend`. 탈출 규칙 1 발동 시 비스트리밍 JSON `{content, evidence_ids, unknowns, tool_calls[]}` | FR-BE-012 |

- 공통 봉투: 성공 `{data, meta}`, 실패 `{error:{code, message}}`, 목록 `?limit=50&cursor=` + `meta.next_cursor`. 코드 예 `ZABBIX_UNAVAILABLE`(503), `NOT_IMPLEMENTED`, `INVALID_CREDENTIALS` (FR-BE-013)
- 역할 기반 접근 제어: 공개(#1), 로그인(#3·#4), viewer 조회, operator(#18 등), admin. viewer 토큰으로 `POST /api/chat` → 403 (FR-BE-003)
- `backend.db` 쓰기 + `shared.db`는 **`ATTACH 'file:/data/shared.db?mode=ro' AS shared`** — 읽기 전용이 연결 수준에서 강제. `INSERT INTO shared.incidents`는 `OperationalError`여야 한다. 모든 연결 `PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON` (FR-BE-014, IF-INT-DB-001)
- `backend.db` 스키마(`users`, `mail_logs`)는 기동 시 `contracts/db-schema.sql`로 멱등 적용 (FR-DATA-003)
- `ZABBIX_MOCK=true`면 Zabbix 대신 fixture (FR-BE-015). Zabbix 호출은 `problem.get, trigger.get, host.get, item.get, history.get, trend.get, apiinfo.version`만, **반드시 `libs/zabbix_ro` 경유**, AI 판단용 조회 없음 (FR-BE-016, 7-4)
- `GET /healthz` 200 (FR-INF-002)

**메일 워커** (DB·메일 담당, `backend/` 안, 구조도상 메일은 Backend 책임 D-03)
- 30초마다 `shared.analysis_reports`와 `backend.mail_logs`를 비교해 아직 안 보낸 리포트를 **1회** 발송(`kind='incident_report'`) (FR-MAIL-001)
- 수신자는 `.env` `MAIL_RECIPIENTS`(쉼표 구분)만. LLM 출력·사용자 입력에서 수신자를 정하지 않음. 리포트가 생긴 장애는 전부 발송(별도 최소 심각도 변수 없음) (FR-MAIL-002, SAFE-16)
- `dedup_key = 'auto:' + report_id + ':' + recipient` UNIQUE → 재시작·중복 폴링에도 수신자당 1통 (FR-MAIL-003)
- 실패 시 3회 재시도 후 `status='failed'`, `attempts`, `error` 기록, 워커는 계속 (FR-MAIL-004)
- 제목 `[DejaFix][<심각도 라벨>] <host_name> - <장애 제목>`. 평문 본문 7항목: ① 리포트 종류(fallback이면 "[LLM 미연결 — 규칙 기반 최소 리포트]") ② 요약 ③ 원인 TOP3(확신도 문자) ④ 확인할 수 없음 목록 ⑤ 계획 단계 수·최고 티어 + "미리보기 — 실행되지 않음" ⑥ `APP_BASE_URL/incidents/{id}` ⑦ 장애 시작·발송 시각(KST). 본문은 **저장된 리포트·계획 값을 옮겨 적기만** 한다(문장 생성·변경 금지, NFR-MAINT-010) (FR-MAIL-005)
- 공급자 스위치 `MAIL_PROVIDER = console | smtp | sendgrid`. `console`은 발송 대신 로그 + `mail_logs(provider='console')` 기록(개발 기본). `smtp`는 `smtp.gmail.com:587` STARTTLS + 앱 비밀번호. 발신 계정 (TODO: 추후결정) (FR-MAIL-006·007)

## 하지 않는 것 (기획서 3-2)
- `shared.db` 쓰기(테이블 작성자는 Agent·Scheduler), LLM 호출, MCP 호출, **분석 판단·원인·티어·분석 문장 생성** — 리포트·계획은 Agent가 저장한 것을 읽기만
- Zabbix 직접 HTTP 호출(`zabbix_ro` 우회), `event.get` 등 7-4 목록 밖 메서드
- 실행 API·필드(`execute`, `run`), 수신자 결정 로직, 비밀값 로그 출력
- [선택]·[이후] 선구현: #2·7·8·9·12·13·14·15·17·19·20·21·22(선택), #16·23·24·25(이후), 감사 로그, 내부 토큰 검증(선택), 시간당 20통 상한(선택)

## 의존 계약
- 제공: `contracts/api.md`(7-1), `contracts/incident.schema.json`(5-5) — 둘 다 Backend 담당 소유. FastAPI OpenAPI와 프론트 MSW가 `api.md`와 일치해야 한다(FR-INF-008)
- 소비: `contracts/agent-api.md`(#18 중계), `contracts/db-schema.sql`(`users`·`mail_logs` 쓰기 / shared 전부 읽기), `libs/zabbix_ro`

## 환경 변수 (이름만)
`BACKEND_DB_PATH`, `SHARED_DB_PATH`, `ZABBIX_URL`, `ZABBIX_API_TOKEN`, `ZABBIX_VERIFY_TLS`, `ZABBIX_MOCK`, `AGENT_URL`, `INTERNAL_TOKEN`(선택), `JWT_SECRET`, `DEMO_ADMIN_PASSWORD`, `DEMO_ONCALL_PASSWORD`, `APP_BASE_URL`, `MAIL_PROVIDER`, `MAIL_RECIPIENTS`, `SMTP_*`, `SENDGRID_API_KEY`, `MAIL_FROM`

## 실행 (uv workspace, 루트에서)
- 로컬: `uv sync` → `uv run --package backend uvicorn dejafix_backend.main:app --port 8000 --reload` (모듈 이름은 골격 PR에서 확정). 메일 워커는 앱 기동과 함께 백그라운드 태스크
- 로컬 개발 기본은 `ZABBIX_MOCK=true`, `MAIL_PROVIDER=console`
- compose: `docker compose -f infra/docker-compose.yml up -d backend`

## 테스트 (PR 머지 조건)
- `uv run ruff check . && uv run ruff format --check . && uv run pytest` (`ZABBIX_MOCK=true`, 임시 DB)
- 반드시 있어야 할 테스트: **ATTACH 쓰기 거부**(`INSERT INTO shared.incidents` → readonly 오류) / **메일 dedup**(같은 리포트에 워커 3회 → 수신자당 1행) / 로그인 성공·실패·역할 403 / `/api/health` Agent 기동 전 `waiting` / #11 응답에 4묶음·근거 ID 일치·`execute` 없음·`mode:"preview"` / `analysis.status` 6값 / Zabbix 차단 시 503 `ZABBIX_UNAVAILABLE` / SMTP 차단 시 `attempts=3`·`failed`
- Incident 응답은 `contracts/incident.schema.json`으로 검증(FR-DATA-006)

## 데모 기준
`ZABBIX_MOCK=false`에서 #5·#6이 실제 Problem을 돌려주고(B3 DoD ①), 장애 상세 #11에 리포트·근거·계획·메일 기록이 한 번에 오며, 리포트 저장 후 40초 안에 메일이 발송된다.
