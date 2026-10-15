# agent — AI Agent (FastAPI :8100, 내부 전용)

주담당 팀장 · 부담당 DB·메일 담당. 규칙 계열(검증·티어·fallback·회귀 세트)은 DB·메일 담당, MCP 접점(클라이언트·고정 수집)은 Zabbix·MCP 담당이 나눠 짓되 PR 승인은 팀장(`docs/work-order.md` W1 Agent).
먼저 읽을 것: 루트 `CLAUDE.md` → `docs/mvp-checklist.md` "Agent" → `contracts/agent-api.md`·`contracts/mcp-tools.md`·`contracts/db-schema.sql` → `packs/it/`.

## 역할 ([필수]만, 근거 = 요구사항 ID)
- **분석 워커** 10초 주기: `shared.db`에서 리포트 없는 장애 중 `severity ≥ ANALYZE_MIN_SEVERITY`(기본 2)를 골라 분석. 장애당 자동 분석 1회, 진행 중이면 중복 시작 안 함, 이미 `resolved`여도 분석 (FR-AG-001)
- **상태 머신** `queued → collecting → analyzing → validating → reported → planning → done`. LLM 미설정·실패·타임아웃은 실패가 아니라 fallback 경로로 계속해 **`done` + `error`**(`LLM_NOT_CONFIGURED | LLM_TIMEOUT | LLM_ERROR | LLM_BUDGET`). `failed`는 리포트를 하나도 못 남긴 경우만 (FR-AG-002)
- **고정 수집 세트**(COLLECTING, LLM 판단 없이 코드가 순서대로): `zabbix_get_problem` → `zabbix_get_host` → `zabbix_list_items`(팩 `metrics.yaml`의 cpu/mem/disk/net 키) → `zabbix_get_history`(트리거 아이템 최근 1시간). 호출마다 `tool_calls` 1행(`ev_` id, args, ok, duration_ms, result_summary, result_json ≤ 32KB, data_clock) (FR-AG-003)
- **LLM 1회 호출**로 리포트 + 계획 초안을 한 JSON으로 받음. `max_tokens` 2000 상수, `LLM_TIMEOUT_SEC=45`. 프롬프트는 `packs/<pack>/prompts/`. **프롬프트에 활성 팩 `actions.yaml`의 허용 동작 목록(id·title·tier)을 넣고 각 단계는 그중 하나를 `action_id`로 고르게** 한다(없을 때만 생략 → 코드가 C) (FR-AG-004)
- **출력 검증**(VALIDATING): ① JSON 스키마 ② 모든 수치·사실의 `evidence_ids`가 비어 있지 않고 실제 `tool_calls`에 존재 ③ 아니면 값 `null` + `unknown_reason` ④ 원인 후보 3개 초과 자름 ⑤ 확신도 `low|medium|high`만 (FR-AG-005, SAFE-08·11)
- **계획 티어 강제**(PLANNING, LLM 재호출 없음): 단계를 `actions.yaml`과 매칭해 **코드가** 티어 지정. LLM이 적은 티어는 무시, 미등록 → C. B는 `precheck`·`rollback` 없으면 C로 강등 + `rationale`에 사유. `change_plans(mode='preview')`·`plan_steps` 저장, `max_tier` 계산. 계획 실패 시 리포트만 유지하고 `agent_runs.error`에 사유 (FR-AG-006·008, SAFE-06·07)
- **fallback 리포트 + fallback 계획**: `LLM_API_KEY`/`LLM_BASE_URL` 빈 값·실패·타임아웃·예산 초과면 수집 사실만으로 `kind='fallback'` 리포트(원인 "확인할 수 없음"), 트리거 아이템 key를 `metrics.yaml` 별칭으로 분류해 `actions.yaml`의 `fallback_plans.<유형>`으로 계획 생성. 분류 불가거나 `fallback_plans`에 목록이 없는 유형(`net` 등)은 A 단계만. 흐름은 계속(메일도 발송). **공급자 보류 중 데모 기본 경로** (FR-AG-007·023, D-05)
- **채팅** `POST /v1/chat` SSE: 맥락(장애·최신 리포트, 필요 시 고정 수집 도구 1~2회) + LLM 1회 응답. LLM 없으면 규칙 기반 답변(최신 리포트 요약, 수집 안 된 질문은 "확인할 수 없음 · NOT_COLLECTED"). 이벤트 `meta`/`final`/`error` 필수, `token`은 LLM 응답일 때, `tool_call`/`tool_result`는 도구를 부른 경우만. `conversations`·`messages`·`tool_calls`·`agent_runs(kind='chat')` 저장, 오류 시 부분 답변 저장. `context.incident_id`가 있으면 장애·리포트 요약을 데이터 블록으로 첨부하고 `conversations.incident_id` 기록 (FR-AG-009·011)
- **MCP 도구 목록 검사**: 기동 시 `tools/list`를 받아 LLM 도구 정의로 변환. 허용 목록은 `contracts/mcp-tools.md`의 도구 이름 12개를 **명시 집합**으로 코드에 둔다(이름 패턴 검사 아님). 밖의 도구가 하나라도 있으면 **기동 실패** + 사유 로그 (FR-AG-010, SAFE-03)
- **LLM 클라이언트**: OpenAI 호환, `LLM_BASE_URL`·`LLM_API_KEY`·`LLM_MODEL`·`LLM_FALLBACK_MODEL`만으로 공급자 교체, 공급자 고유 의존 없음. 키 없이도 기동·분석(fallback)되어야 함. 동작 모드 우선순위: ① `LLM_FAKE=true` 가짜 LLM(고정 JSON, `agent_runs.model='fake'`, 테스트·개발 전용, **데모 금지**) ② 키·URL 빈 값 → fallback ③ 둘 다 있음 → 실 LLM 1회 (FR-AG-012·013)
- **호출자 기록** `agent_runs.caller`(`worker | backend | claude | agent:<name>`), `requested_by`(`X-User-Id`) (FR-AG-014)
- **도메인 팩 로더**: 기동 시 `packs/${DOMAIN_PACK}/`의 `metrics.yaml`·`actions.yaml`·`prompts/`를 읽어 메모리에 둔다. 팩이 없거나 읽기 실패면 기동 실패. 상태 머신·검증·티어 코드는 팩 내용으로만 동작하고 IT 전용 값을 갖지 않는다 (FR-AG-025, NFR-EXT-001·002)
- **공유 스키마 멱등 적용**: 기동 시 `contracts/db-schema.sql`(전 문장 `IF NOT EXISTS`)을 `shared.db`에 실행. Scheduler도 같은 일을 하므로 순서 무관 (FR-DATA-003)
- `GET /healthz` → `{ok, model, mcp:{zabbix:"ok"}}` (IF-INT-AG-001)
- 안전 회귀 세트: SAFE-06·07 테스트를 `@pytest.mark.safety_regression`으로 묶고 "잘못 통과 x/N, 과잉 차단 y/M" 출력 (NFR-EVAL-001)

## 하지 않는 것 (기획서 3-2, SAFE-05)
- 화면, 사용자 인증, 메일 발송, Backend 호출(역방향 금지)
- **Zabbix 직접 호출** — 반드시 mcp-zabbix 도구로만. `libs/zabbix_ro`도 Agent에서는 쓰지 않는다
- 셸·SSH·임의 HTTP 도구(`subprocess`, `paramiko`, 임의 `httpx` 도구) — 도구는 MCP 목록뿐
- 실행 경로: `execute`/`run` 필드·API·명령 실행 없음. `change_plans.mode`는 `'preview'`만
- 티어를 LLM이 정하게 두는 것, 미등록 동작을 A/B로 두는 것
- `incidents`·`scheduler_jobs`(Scheduler 소유)와 `backend.db` 쓰기
- 엔진 코드에 IT 전용 아이템 키·동작 ID·동작 제목·명령 문구 하드코딩(루트 CLAUDE.md ⑨ `rg` 검사 0건)
- [선택]·[이후] 선구현: 다시 분석 API, 런 상태 API, LLM 추가 도구 호출·채팅 도구 루프, 폴백 모델 재시도, 토큰·비용 기록, 7일 재발 횟수, 계획 단독 생성, Agent 자체 MCP 서버

## 의존 계약
- 제공: `contracts/agent-api.md`(`/healthz`, `/v1/chat` SSE, 리포트·계획 JSON Schema, `unknown_reason` 변환표)
- 소비: `contracts/mcp-tools.md`(도구 이름·인자·공통 봉투), `contracts/db-schema.sql`(`agent_runs, tool_calls, analysis_reports, change_plans, plan_steps, conversations, messages` 쓰기 / `incidents` 읽기), `packs/<pack>/`(`packs/README.md`)
- `unknown_reason` 변환(IF-INT-MCP-001): `NO_PERMISSION→NO_PERMISSION`, `NOT_FOUND→NO_DATA`, `ZABBIX_ERROR·타임아웃→TOOL_ERROR`, 빈 결과→`NO_DATA`, `stale:true→STALE`, 고정 수집 세트에 없는 항목→`NOT_COLLECTED`

## 환경 변수 (값은 `.env`, 여기엔 이름만)
`SHARED_DB_PATH`, `MCP_ZABBIX_URL`, `INTERNAL_TOKEN`(선택), `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_FALLBACK_MODEL`, `LLM_TIMEOUT_SEC`, `LLM_FAKE`, `LLM_DAILY_BUDGET_USD`, `DOMAIN_PACK`, `ANALYZE_MIN_SEVERITY`

## 실행 (uv workspace, 루트에서)
- 로컬: `uv sync` → `uv run --package agent uvicorn dejafix_agent.main:app --port 8100 --reload` (패키지·모듈 이름은 골격 PR에서 확정, 명명 규칙은 snake_case `dejafix_agent`)
- 워커는 앱 기동과 함께 백그라운드 태스크로 시작한다(별도 프로세스 없음)
- compose: `docker compose -f infra/docker-compose.yml up -d agent` (빌드 컨텍스트는 저장소 루트, `packs/`가 이미지에 포함돼야 함)

## 테스트 (PR 머지 조건)
- `uv run ruff check . && uv run ruff format --check . && uv run pytest` — 실 LLM·실 Zabbix 없이 통과해야 한다(`LLM_FAKE=true`, 목 MCP)
- 반드시 있어야 할 테스트: SAFE-03 쓰기 도구 포함 목 MCP → 기동 거부 / SAFE-06 미등록 `action_id` → C / SAFE-07 `clean_temp_files`에 rollback 없음 → C + 사유, LLM이 `tier:'A'`라 적은 `reboot_host` → C / SAFE-08 근거 없는 수치 `93.4` → `null`, 없는 `ev_zz` 참조 → `null`, 원인 5개 → 3개, `confidence:"87%"` → 스키마 거부 / FR-AG-001 같은 incident에 run 2개 안 생김, severity 1은 run 없음 / FR-AG-002 LLM 예외 주입 → `done`+`error`+`kind='fallback'` / FR-AG-025 시험 팩(`DOMAIN_PACK=test`)으로 분석 → 시험 팩의 동작 ID·키 사용, 팩 없음 → 기동 실패
- `uv run pytest -m safety_regression` → "잘못 통과 0/N" (D-NUMBERS 장면에 사용)
- 하드코딩 검사(루트 CLAUDE.md ⑨) 0건

## 데모 기준
주입 → 60초 안에 `analysis_reports`·`change_plans`·`plan_steps` 행이 생기고 run은 `done`. 공급자 미확정이면 `kind='fallback'` + 규칙 기반 계획으로 같은 흐름(요구사항 2-2). 가짜 LLM은 데모에 쓰지 않는다.
