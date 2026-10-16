# PLAN-frontend-api — 프론트 데이터 형식 전환·API 연동 작업 큐

- 파트: frontend-api (담당 연동·인프라 담당, 부 화면 담당) / 폴더: `frontend/`만
- 기준: `docs/mvp-checklist.md`, `docs/plan.md` 7장(API 계약)·4-2(화면), `docs/requirements.md` FR-FE, `contracts/api.md`(머지되면 이것이 우선)
- 위에서부터 하나씩 처리한다. 항목마다 `npm run lint`, `npx tsc --noEmit`, `npm run build` 통과 후 커밋 1개.
- 실패 2번이면 `[BLOCKED]`로 바꾸고 사유를 `LOG-frontend-api.md`에 쓴다.
- 원칙: **데이터 형식은 기획서 7장 기준으로 바꾸고, 화면 구성은 살린다.** 새 기능·새 화면을 만들지 않는다.

## 건드리지 않는 것
- 평소 범위·디스크 예측·추이·히트맵·서버 간 묶음(현황 홈 위젯), 서버 비교(`/compare`), 비용 절감(`/cost`) — 화면만 있음, API는 이후. 목 데이터 그대로 둔다.
- 변경 계획 목록·리포트·알림·관리자 화면 — [선택]/[이후]. 이번 큐에서 제외.
- `contracts/`, `.env`, 다른 파트 폴더. 계약과 다른 점이 보이면 LOG에 "계약 변경 제안"으로만 남긴다.

## 작업 큐

- [x] **0-p. prettier**: devDependency 추가(`prettier@^3.9.10`), `frontend/.prettierrc`(semi 없음·작은따옴표·120자) — 10/15 완료
- [x] **0. 준비**: `msw`를 devDependency로 추가(`npm install -D msw`) (기획서 13-1)
- [x] **1. Vite `/api` 프록시**: `vite.config.ts`에 `server.proxy['/api'] = 'http://localhost:8000'`. 코드에서 API 주소는 상대경로 `/api`만 쓰고 `VITE_API_BASE_URL` 같은 절대 주소 변수는 쓰지 않는다 (IF-INT-FE-002, FR-FE-016)
- [x] **2. `types.ts`를 기획서 7장 형식으로**: 기존 목업 타입은 범위 밖 화면용으로 남기고, 계약 타입을 추가·전환 (FR-DATA-006, IF-INT-BE)
  - [x] 공통 봉투 `ApiOk<T> = {data, meta}`, `ApiError = {error:{code, message}}`, 커서 `meta.next_cursor`
  - [x] `Measured = {value: number|null, unit, collected_at, unknown: boolean, unknown_reason?: 'NO_DATA'|'STALE'|'TOOL_ERROR'|'NO_PERMISSION'|'NOT_COLLECTED'}`
  - [x] `Incident`(5-5 표준 형식: `id, source, zabbix{eventid,triggerid,hostid}, host{id,name}, title, severity{level,label}, status, started_at, resolved_at, tags[], analysis{status, report_id, plan_id}`), `analysis.status` 6값 `skipped|pending|running|done|fallback|failed`
  - [x] `DashboardSummary`(#5: `active_incidents, high_incidents, hosts{ok,total,unknown}, reports_today, avg_analysis_sec` 각 `Measured`), `Health`(#4), `Problem`(#6), `User`·`LoginResponse`(#1·#3)
  - [x] `IncidentDetail`(#11: `incident, report{id, version, kind:'llm'|'fallback', summary, impact, causes[≤3]{rank,title,confidence:'low'|'medium'|'high',reasoning,evidence_ids,verify}, facts[], unknowns[], next_checks[], created_at}, evidence: ToolCall[], plan{id,title,goal,mode:'preview',max_tier,assumptions[]}, steps[], mail_logs[]`)
  - [x] `PlanStep`(`seq, action_id, title, target, command_preview, tier:'A'|'B'|'C', rationale, precheck, expected_effect, risk, rollback, evidence_ids[]`) — `execute`/`run` 필드 없음 (SAFE-04)
  - [x] `ToolCall`(`id 'ev_…', tool, args, ok, duration_ms, result_summary, data_clock, called_at`), `MailLog`(`recipient, status sent|failed|skipped, attempts, error, sent_at`)
  - [x] 채팅 SSE 이벤트 타입 `meta|tool_call|tool_result|token|final|error`(7-2), 비스트리밍 `{content, evidence_ids, unknowns, tool_calls[]}`
  - [x] 확신도는 문자 3단계만, 퍼센트·점수 필드 없음 (SAFE-11)
- [x] **3. `UnknownValue` 컴포넌트**: `Measured.unknown=true` 또는 `value=null`을 "확인할 수 없음 · 사유 · 수집 시각(KST hh:mm)"으로 표시. 0·빈칸·NaN 금지. KPI 카드·리포트 facts에 적용 (FR-FE-010, SAFE-10)
- [x] **4. `EvidenceTrace`를 `tool_calls` 형식으로**: 입력을 `ToolCall[]`로 바꾸고 tool·args·called_at·duration_ms·result_summary·data_clock 표시, 리포트의 `evidence_ids` 클릭 → 해당 행 강조 (FR-FE-007, SAFE-12)
- [x] **5. MSW 필수 API 8개**: `src/mocks/`에 #1 login, #3 me, #4 health, #5 dashboard/summary, #6 problems, #10 incidents, #11 incidents/{id}, #18 chat(SSE 스트림 목) 핸들러. 개발 모드에서만 기동, 백엔드 없이 필수 화면 전부 렌더·콘솔 오류 없음. 목 데이터에 `unknown:true` 값, fallback 리포트, A·B·C 단계, `failed` 메일 1건 포함 (FR-FE-015)
- [x] **6. `sessionStorage` 전환·로그인 연동**: `AuthProvider`의 `localStorage` → `sessionStorage`, 저장 내용은 JWT + `user{id, username, role, display_name}`. `POST /api/auth/login`·`GET /api/auth/me` 사용, 401이면 로그아웃·`/login` 이동. 키·토큰을 그 밖의 저장소에 두지 않는다 (FR-FE-001, NFR-SEC-005)
- [x] **7. `api.ts` fetch 전환 + 15초 폴링**: 필수 화면이 쓰는 함수만 `fetch('/api/…')` + `Authorization: Bearer <JWT>`로 교체, 봉투 해제·`error.code` 처리(`ZABBIX_UNAVAILABLE` → 배너). react-query `refetchInterval: 15000`을 현황 홈·장애 상세·연결 상태에 적용. 범위 밖 화면 함수(`baselines`, `diskForecasts`, `trend`, `heatmap`, `crossGroups`, `costItems`, `servers` 등)는 목 그대로 둔다 (FR-FE-002~004·012)
- [x] **8. 현황 홈·장애 상세를 새 타입으로**: 화면 구성은 유지하고 데이터만 교체 — KPI 4종(`Measured`), 장애 목록(#10·#6), 상세 리포트·EvidenceTrace·계획 미리보기(A 초록 "조회 · 안전" / B 주황 "변경 · 승인 필요(미구현)" / C 빨강 "금지 · 사람이 판단", ReadOnlyNotice, 실행 버튼 없음)·메일 발송 기록. 원인 후보의 "검증 결과(확인/반증)" 표시는 계약에 없으므로 확신도·근거로 바꾼다. 다시 분석·메일 재발송·검토 버튼은 렌더하지 않는다 (FR-FE-003·004·006·008·009)
- [x] **9. 채팅 `fetch` 스트림**: `askAssistant`를 `POST /api/chat` + `fetch` ReadableStream SSE 파서로 교체(`EventSource` 금지). `token`은 순차 표시, `meta`→`final`만 와도 정상, `final.unknowns`·`evidence_ids` 표시, `error` 이벤트 처리, 장애 상세에서 열면 `context.incident_id` 첨부. 응답이 JSON이면 비스트리밍으로 같은 레이아웃 표시(탈출 규칙 1) (FR-FE-011·014)
- [x] **10. 마무리 점검**: DOM에 "실행·Run·Execute" 버튼 없음, 번들에 키 문자열 없음, localStorage에 토큰 없음, 엔진 하드코딩 `rg` 0건(루트 CLAUDE.md ⑨), `frontend/.nvmrc`(`22`)·`engines.node`(">=22 <23") 확인(13-1) — 결과를 LOG에 기록
