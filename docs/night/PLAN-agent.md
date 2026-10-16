# PLAN-agent — AI Agent 작업 큐 (담당 팀장, 부 DB·메일 담당 / 폴더 `agent/`, `packs/it/`)

- 기준: `agent/CLAUDE.md`, `packs/it/README.md`, `docs/mvp-checklist.md` "Agent", `contracts/agent-api.md`·`mcp-tools.md`·`db-schema.sql`(머지 전엔 기획서 4-5·6-3·7-2·7-3)
- 항목마다 `uv run ruff check . && uv run ruff format --check . && uv run pytest` 통과 후 커밋 1개. 실패 2번이면 `[BLOCKED]` + `LOG-agent.md`
- 개발 기본 `LLM_FAKE=true`, 목 MCP(mcp-zabbix fixture 또는 테스트 더블). 야간에는 실 LLM·실 Zabbix 호출 금지
- 낮에 사람 셋이 나눠 짓는 부분(`docs/work-order.md` W1 Agent)과 겹치지 않게, 루프는 **사람이 끝내지 못한 항목만** 큐에 남긴다. 퇴근 전 큐를 정리할 것

## 작업 큐
- [ ] **1. 팩 파일 초안** (DR-021, 기획서 6-3·7-3): `packs/it/metrics.yaml`(cpu·mem·disk·net 별칭. 실제 키는 기술 확인 항목(G2)이라 Windows 템플릿 후보 키를 적고, 팀장이 데모 PC에서 확인한 값으로 교체), `packs/it/actions.yaml`(6-3 초안 그대로: B 동작에 precheck·rollback, `default_tier: C`, `fallback_plans` cpu/mem/disk), `packs/it/prompts/`(analyze·chat 시스템 프롬프트, 허용 동작 목록 삽입 자리). YAML 파싱·`fallback_plans` ID 존재 테스트
- [ ] **2. 골격·팩 로더** (FR-AG-025, NFR-EXT-001·002, IF-INT-AG-001): FastAPI 앱, `GET /healthz`, `packs/${DOMAIN_PACK}/` 로더(없으면 기동 실패 + 사유). **테스트: `packs/test/` 시험 팩으로 분석 → 시험 팩의 `action_id`·키 사용, 팩 없음 → 비정상 종료**
- [ ] **3. 공유 스키마 적용·DB 접근**: `contracts/db-schema.sql` 멱등 적용(Scheduler와 같은 모듈), WAL·busy_timeout·foreign_keys, Agent 소유 7테이블 쓰기 함수
- [ ] **4. MCP 클라이언트·도구 목록 검사** (FR-AG-010, SAFE-03·05): streamable HTTP로 `tools/list` → 허용 목록 **명시 집합 12개**와 대조, 밖의 도구가 있으면 기동 실패. LLM 도구 정의 변환. **테스트: 목 MCP에 `zabbix_update_host` 포함 → 종료 코드·사유 로그; 5개만이면 기동**
- [ ] **5. 상태 머신·워커** (FR-AG-001·002·014, NFR-SAFE-018): 10초 폴링, 선정 조건(리포트 없음·severity ≥ `ANALYZE_MIN_SEVERITY`·resolved 포함·진행 중 제외), `agent_runs` 상태 전이 `queued→collecting→analyzing→validating→reported→planning→done`, `caller='worker'`, run 60초·도구 12회 상한. **테스트: 같은 incident run 2개 안 생김, severity 1 run 없음, DB 쓰기 실패 주입 → `failed`**
- [ ] **6. 고정 수집 세트** (FR-AG-003): `zabbix_get_problem → zabbix_get_host → zabbix_list_items(팩 키) → zabbix_get_history(트리거 아이템 1h)` 순서, 각 호출 `tool_calls` 저장(`ev_` id, `result_json` ≤32KB, 실패도 `ok=0`), MCP 봉투 → `unknown_reason` 변환표 적용. 테스트: 4행·32KB
- [ ] **7. fallback 리포트 + fallback 계획** (FR-AG-007·023, NFR-AVAIL-003): 키 빈 값이면 LLM 호출 없이 사실만으로 `kind='fallback'` 리포트(원인 "확인할 수 없음"), 트리거 키 → 별칭 분류 → `fallback_plans.<유형>`으로 계획, 목록 없는 유형(`net`)·분류 불가는 A 단계만, run `done`+`error=LLM_NOT_CONFIGURED`. **테스트: CPU 장애 → `change_plans(mode='preview')` 1행, B 단계에 precheck·rollback**
- [ ] **8. 계획 티어 강제** (FR-AG-006·008, SAFE-06·07): `actions.yaml` 매칭, LLM 티어 무시, 미등록 → C, B에 precheck/rollback 없으면 C + `rationale`, `max_tier`. 계획 스키마 위반 시 리포트만 유지 + `error`. **테스트 3종(머지 조건): 미등록 → C / `clean_temp_files` rollback 없음 → C+사유 / LLM `tier:'A'`인 `reboot_host` → C**
- [ ] **9. 안전 회귀 세트** (NFR-EVAL-001): 8번 테스트를 `@pytest.mark.safety_regression`으로 묶고 위험 N개·안전 M개 입력, 출력 "잘못 통과 x/N, 과잉 차단 y/M". `pyproject`에 마커 등록
- [ ] **10. LLM 클라이언트·가짜 LLM·1회 호출** (FR-AG-004·012·013, IF-EXT-002): OpenAI 호환(`openai` 클라이언트, `LLM_BASE_URL`·`LLM_API_KEY`·`LLM_MODEL`), `LLM_FAKE=true`면 고정 JSON(`model='fake'`), `max_tokens=2000`, `LLM_TIMEOUT_SEC=45`, 타임아웃·예외 → fallback 경로 + `error` 사유. 프롬프트에 **허용 동작 목록(id·title·tier)** 삽입. 테스트: run당 LLM 호출 1건, 가짜 응답의 `action_id`가 전부 `actions.yaml`에 있음
- [ ] **11. 출력 검증** (FR-AG-005, SAFE-08·11): 스키마 검증(`agent-api.md` JSON Schema), 근거 ID 실존 확인, 없으면 `null`+`unknown_reason`, 원인 ≤3, 확신도 3단계. **테스트 4종(머지 조건): `93.4` 근거 없음 → null / `ev_zz` → null / 원인 5 → 3 / `"87%"` 거부**
- [ ] **12. 채팅 `/v1/chat`** (FR-AG-009·011, IF-INT-AG-002): SSE `meta → (token…) → final` / `error`, 규칙 기반 답변(LLM 없음: 최신 리포트 요약 + 수집 안 된 질문 → `unknowns[{label, reason:"NOT_COLLECTED"}]`), `context.incident_id` 첨부, `conversations`·`messages`·`agent_runs(kind='chat', caller='backend', requested_by)` 저장, 오류 시 부분 답변 저장. 테스트: "이 서버 백업 작업이 원인인가?" → NOT_COLLECTED
- [ ] **13. 마무리**: 하드코딩 `rg` 0건(팩 값만), `subprocess`·`paramiko`·임의 httpx 도구 없음, LOG 기록
