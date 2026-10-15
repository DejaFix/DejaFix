# PLAN-backend — Backend API·`libs/zabbix_ro` 작업 큐 (담당 Backend 담당, 부 연동·인프라 담당 / 폴더 `backend/`, `libs/zabbix_ro/`)

- 기준: `backend/CLAUDE.md`, `libs/zabbix_ro/CLAUDE.md`, `docs/mvp-checklist.md` "Backend", `contracts/api.md`·`incident.schema.json`·`agent-api.md`·`db-schema.sql`(머지 전엔 기획서 5·7장)
- 항목마다 `uv run ruff check . && uv run ruff format --check . && uv run pytest` 통과 후 커밋 1개. 실패 2번이면 `[BLOCKED]` + `LOG-backend.md`
- 개발 기본: `ZABBIX_MOCK=true`, `MAIL_PROVIDER=console`, 임시 DB. 실 Zabbix·실 메일 호출 금지(야간)
- 메일 워커 모듈은 `PLAN-scheduler-db.md`(DB·메일 담당) 큐. 여기서는 건드리지 않는다

## 작업 큐
- [ ] **1. FastAPI 골격** (FR-BE-013, FR-INF-002): 앱 팩토리, `GET /healthz`, 공통 응답 봉투 `{data, meta}` / `{error:{code,message}}`, 커서 페이지네이션 유틸, 오류 코드 상수(`ZABBIX_UNAVAILABLE`, `NOT_IMPLEMENTED`, `INVALID_CREDENTIALS`)
- [ ] **2. DB 연결** (FR-BE-014, FR-DATA-003·004): `backend.db` 열기 + `PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON`, `contracts/db-schema.sql`의 backend 부분 멱등 적용, `ATTACH 'file:…/shared.db?mode=ro' AS shared`. `shared.db`가 없으면 예외 대신 `waiting` 상태 유지·요청마다 재시도. **테스트: `INSERT INTO shared.incidents` → readonly 오류**(머지 조건)
- [ ] **3. 로그인·me·역할** (FR-BE-001·002·003, NFR-SEC-004): bcrypt 해시, 시드 `admin`·`oncall`(`.env` 비밀번호), JWT 발급(`JWT_SECRET`), `GET /api/auth/me`, 역할 의존성(viewer/operator/admin). 테스트: 성공 200+JWT, 실패 401 `INVALID_CREDENTIALS`, viewer로 `POST /api/chat` → 403
- [ ] **4. `libs/zabbix_ro`** (FR-LIB-001·002·003): `call(method, params)`, 허용 목록 13개 밖은 요청 전 `MethodNotAllowed`, `Authorization: Bearer`, 본문에 `auth` 없음, `ZABBIX_MOCK=true` fixture(Zabbix 7.0 형식 `problem.get, trigger.get, host.get, item.get, history.get, apiinfo.version`). **테스트: `host.update`·`item.create`·`user.login`·`problem.delete` 거부, `problem.get` 통과**(SAFE-02, 머지 조건)
- [ ] **5. `GET /api/health`** (FR-BE-004): zabbix(`apiinfo.version`)·agent(`/healthz`)·mcp_zabbix(`/healthz`)·shared_db(`ok`/`waiting`)·backend_db·`scheduler_last_ok`(`shared.scheduler_jobs.poll_problems.last_ok_at`). 어느 하나 실패해도 200
- [ ] **6. `GET /api/dashboard/summary`** (FR-BE-005): KPI 4종 `Measured`. 정의는 `backend/CLAUDE.md` 표. Zabbix 실패 시 Zabbix 의존 KPI만 `unknown:true, TOOL_ERROR`, shared 의존 KPI는 값 유지
- [ ] **7. `GET /api/problems`** (FR-BE-006): `problem.get`(recent, severities) + `trigger.get(selectHosts)`로 호스트 보강, `shared.incidents.zabbix_eventid`로 `incident_id` 매칭(null 가능)
- [ ] **8. `GET /api/incidents`** (FR-BE-008, FR-DATA-006): 표준 Incident 형식(`contracts/incident.schema.json`)으로 변환, `analysis{status, report_id, plan_id}` JOIN — status 6값 규칙(`skipped` severity < `ANALYZE_MIN_SEVERITY` / `pending` run 없음 / `running` queued~planning / `done` kind=llm / `fallback` kind=fallback / `failed` 리포트 없이 failed). 커서·필터 `status`, `severity_min`. 테스트: 응답이 스키마 검증 통과
- [ ] **9. `GET /api/incidents/{id}`** (FR-BE-009): `{incident, report(최신 version), evidence[tool_calls], plan, steps[], mail_logs[]}` 한 번에. 테스트: `causes[].evidence_ids` ⊆ `evidence[].id`, 응답에 `execute`·`run` 키 없음, `plan.mode == "preview"`
- [ ] **10. `POST /api/chat` 중계** (FR-BE-012): operator만. Agent `/v1/chat`에 `{conversation_id?, message, context, caller:"backend"}` + 헤더 `X-User-Id`·`X-User-Role`(+`X-Internal-Token` 선택) → `text/event-stream`을 **그대로** 중계(버퍼링 없이). Agent 오류 시 `error` 이벤트. 환경 변수(또는 설정)로 비스트리밍 모드 전환 시 `{content, evidence_ids, unknowns, tool_calls[]}` JSON
- [ ] **11. 오류·가용성** (FR-BE-013, NFR-AVAIL-004): Zabbix 다운 상태에서 `/api/problems` → 503 `ZABBIX_UNAVAILABLE`, 서비스는 생존. `zabbix_ro` 외 Zabbix HTTP 호출 없음 확인(`rg httpx backend/` 결과가 agent 중계뿐)
- [ ] **12. 마무리**: OpenAPI(`/docs`)의 8개 엔드포인트가 `contracts/api.md`와 일치하는지 대조표를 LOG에 기록. 엔진 하드코딩 `rg` 0건
