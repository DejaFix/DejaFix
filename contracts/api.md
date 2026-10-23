# Backend REST 계약 v0 (`contracts/api.md`)

- 소유자: Backend 담당 / 승인: 연동·인프라 담당(프론트 소비자) — 계약 PR은 2인 승인
- 원본: `docs/plan.md` 7-1, 노션 「DejaFix 프론트 API 요청서」 3장, `docs/requirements.md` 6-2(IF-INT-BE)
- 함께 보는 계약: `incident.schema.json`(Incident 형식), `agent-api.md`(#18의 Agent 쪽), `db-schema.sql`(저장 형식)
- 범위: **[필수] 8개** (#1·#3·#4·#5·#6·#10·#11·#18). [선택]·[이후] API는 `docs/plan.md` 7-1 표를 따르며 여기에 상세를 적지 않는다(필수 완료 후 추가).
- 상태: **v0** — 요청서 5장 확인 요청 8건은 Issue #23의 제안을 모두 수락해 아래 4장에 반영했다. 구현은 PR #37(dev 머지)이 이 형식을 따른다.

## 1. 공통 규칙

| 항목 | 규칙 |
|---|---|
| 경로 | 접두사 `/api`, 본문 JSON(UTF-8). `GET /healthz`(접두사 없음, 인증 없음)는 프로세스 생존 확인용 `{"status":"ok"}` |
| 인증 | `Authorization: Bearer <JWT>` (로그인 제외 전부). JWT 는 프론트가 `sessionStorage` 에 보관 |
| 성공 | `{ "data": ..., "meta": {...} }` |
| 실패 | `{ "error": { "code": "...", "message": "..." } }` + HTTP 상태. 스택 트레이스는 넣지 않는다 |
| 목록 | `?limit=50&cursor=` (limit 1~100, 기본 50). 다음 쪽 커서는 `meta.next_cursor`(없으면 `null`). 커서는 불투명 문자열 |
| 시각 | 전부 **UTC ISO 8601** `2026-10-16T01:20:00Z`(`YYYY-MM-DDTHH:MM:SSZ`, 소수 초 없음 — DB 저장 형식과 같다). KST 변환은 프론트 |
| 응답 속도 | 프론트가 현황 홈·장애 상세를 15초마다 다시 부른다 → 1초 안에 응답 |
| 확인할 수 없는 값 | **0이나 빈 문자열로 보내지 않고** `Measured`(아래)로 보낸다 (SAFE-10) |
| 실행 금지 | 어떤 응답에도 `execute`·`run` 필드가 없다. `plan.mode` 는 항상 `"preview"` (SAFE-04) |

### Measured — 화면에 숫자로 보이는 값의 공통 타입

```json
{ "value": 93.4, "unit": "%", "collected_at": "2026-10-16T01:19:30Z", "unknown": false }
{ "value": null, "unit": "%", "collected_at": "2026-10-16T00:40:00Z", "unknown": true, "unknown_reason": "STALE" }
```

`unknown_reason`: `NO_DATA | STALE | TOOL_ERROR | NO_PERMISSION | NOT_COLLECTED`

### 역할 (viewer < operator < admin)

| 엔드포인트 | 최소 역할 |
|---|---|
| #1 로그인 | 공개 |
| #3 me, #4 health | 로그인(viewer 이상) |
| #5·#6·#10·#11 | viewer |
| #18 채팅 | **operator** (viewer → 403) |

### 오류 코드

| HTTP | code | 쓰이는 곳 / 프론트 동작 |
|---|---|---|
| 401 | `INVALID_CREDENTIALS` | #1. "아이디 또는 비밀번호가 틀렸습니다" |
| 401 | `UNAUTHORIZED` | 토큰 없음·만료·위조. 토큰 삭제 후 `/login` |
| 403 | `FORBIDDEN` | 역할 부족(예: viewer 의 #18). "권한이 없습니다" |
| 404 | `NOT_FOUND` | #11 없는 장애. 알 수 없는 경로 |
| 422 | `VALIDATION_ERROR` | 요청 본문·쿼리 형식 오류, 잘못된 `cursor` |
| 502 | `AGENT_UNAVAILABLE` | #18 비스트리밍에서 Agent 연결 실패·중단. 스트림 모드는 `event: error` |
| 503 | `ZABBIX_UNAVAILABLE` | #6 Zabbix 조회 실패. 상단 경고 배너 |
| 503 | `ORCHESTRATOR_UNAVAILABLE` | #26·#27 총괄이 연결되지 않았거나 응답하지 않음. 화면은 "확인할 수 없음" |
| 503 | `SHARED_DB_UNAVAILABLE` | #10·#11 `shared.db` 가 아직 없음(Agent·Scheduler 기동 전). 요청마다 재시도 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 서버 오류 |

Agent 가 스트림을 열기 전에 거절한 오류(`CONVERSATION_NOT_FOUND`, `BAD_REQUEST` 등)는 #18 이 상태 코드와 `error` 를 그대로 전달한다(`agent-api.md` 1-2).

## 2. 엔드포인트 요약

| # | 메서드·경로 | 최소 역할 | 데이터 출처 |
|---|---|---|---|
| 1 | `POST /api/auth/login` | 공개 | backend.db `users` |
| 3 | `GET /api/auth/me` | 로그인 | backend.db `users` |
| 4 | `GET /api/health` | 로그인 | Zabbix·Agent·MCP 상태, 두 DB, `scheduler_jobs` |
| 5 | `GET /api/dashboard/summary` | viewer | Zabbix + shared.db |
| 6 | `GET /api/problems` | viewer | Zabbix `problem.get`+`trigger.get` |
| 10 | `GET /api/incidents` | viewer | shared.db `incidents` + JOIN |
| 11 | `GET /api/incidents/{id}` | viewer | shared.db + backend.db `mail_logs` |
| 18 | `POST /api/chat` | operator | Agent `/v1/chat` SSE 중계 |

개발 순서: #1 → #3 → #4 → #10 → #11 → #5 → #6 → #18.

## 3. 필수 8개 상세

### #1 `POST /api/auth/login`

요청 `{ "username": "oncall", "password": "••••••" }`

응답 200
```json
{
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": { "id": 2, "username": "oncall", "role": "operator", "display_name": "당직자" }
  },
  "meta": { "expires_at": "2026-10-16T09:20:00Z" }
}
```
- 401 `INVALID_CREDENTIALS`. 사용자 없음과 비밀번호 틀림을 구분하지 않는다.
- `user.role`(`admin | operator | viewer`)은 프론트가 메뉴·버튼 권한에 그대로 쓴다. `display_name` 은 `null` 일 수 있다.
- 시드: `admin`(admin)·`oncall`(operator). 비밀번호는 `.env` `DEMO_ADMIN_PASSWORD`·`DEMO_ONCALL_PASSWORD` 로 Backend 가 기동 시 만든다.

### #3 `GET /api/auth/me`

응답 200
```json
{ "data": { "id": 2, "username": "oncall", "role": "operator", "display_name": "당직자", "email": "oncall@example.com" }, "meta": {} }
```
- 토큰이 없거나 만료면 401 `UNAUTHORIZED` → 프론트가 토큰을 지우고 `/login` 으로 보낸다.

### #4 `GET /api/health`

구성요소 하나가 죽어도 **200** 으로 상태만 알린다.
```json
{
  "data": {
    "zabbix": "ok", "agent": "ok", "mcp_zabbix": "down",
    "shared_db": "waiting", "backend_db": "ok",
    "scheduler": "ok", "scheduler_last_ok": "2026-10-16T01:20:30Z"
  },
  "meta": { "checked_at": "2026-10-16T01:20:41Z" }
}
```
- 값은 `"ok" | "down"`. `shared_db` 만 `"waiting"`(shared.db 파일이 아직 없음, 요청마다 재시도), `scheduler` 만 `"stale"` 이 더해진다.
- `scheduler_last_ok` = `shared.scheduler_jobs` 의 `job='poll_problems'` `last_ok_at`. 기록이 없거나 shared.db 가 없으면 `null`.
- `zabbix` 는 `apiinfo.version` 한 번(인증 없는 읽기)으로 판정한다. Zabbix 가 느려도 health 가 같이 느려지지 않도록 **3초 안에 답이 없으면 `"down"`**. `ZABBIX_MOCK=true` 면 항상 `"ok"`.
- `scheduler` = 수집기가 살아 있는지의 판정. 응답을 만드는 시각과 `scheduler_last_ok` 의 차이가 **`SCHEDULER_STALE_SEC` 이내면 `"ok"`**, 그보다 오래됐으면 `"stale"`(수집이 멈춘 것으로 본다), `scheduler_last_ok` 가 `null` 이면 `"down"`. `SCHEDULER_STALE_SEC` 기본값은 **90**(폴링 주기 `INCIDENT_POLL_SEC=30` × 3)이다. 화면은 이 값으로 "수집 중단" 배너를 띄운다.

### #5 `GET /api/dashboard/summary`

KPI 4종, **모든 값이 `Measured`**.
```json
{
  "data": {
    "active_incidents": { "value": 1, "unit": "건", "collected_at": "2026-10-16T01:20:30Z", "unknown": false },
    "high_incidents":   { "value": 1, "unit": "건", "collected_at": "2026-10-16T01:20:30Z", "unknown": false },
    "hosts": {
      "ok":      { "value": 2, "unit": "대", "collected_at": "2026-10-16T01:20:35Z", "unknown": false },
      "total":   { "value": 3, "unit": "대", "collected_at": "2026-10-16T01:20:35Z", "unknown": false },
      "unknown": { "value": 1, "unit": "대", "collected_at": "2026-10-16T01:20:35Z", "unknown": false }
    },
    "reports_today":    { "value": 2, "unit": "건", "collected_at": "2026-10-16T01:20:40Z", "unknown": false },
    "avg_analysis_sec": { "value": null, "unit": "s", "collected_at": "2026-10-16T01:20:40Z", "unknown": true, "unknown_reason": "NO_DATA" },
    "llm_usage_today": null
  },
  "meta": { "generated_at": "2026-10-16T01:20:41Z" }
}
```
- 활성 장애 = `incidents.status='problem'` 수. High 이상 = severity ≥ 4(High·Disaster).
- 감시 호스트 = Zabbix 감시 중(`status=0`) 호스트 수. 정상 = 에이전트 가용성 1 이고 활성 Problem 0, 확인 불가 = 가용성 0 → `hosts.unknown` 에 따로 센다.
- 오늘 리포트 수·평균 분석 시간의 "오늘" = **KST 자정 기준**.
- Zabbix 가 끊기면 `hosts.*` 는 `unknown:true, unknown_reason:"TOOL_ERROR"`, shared.db 기준 KPI 는 값을 유지한다. Zabbix 가 5초 안에 답하지 않아도 같다(API 5번 자체는 200 으로 즉시 답한다).
- Zabbix 조회 결과는 **성공 5초·실패 2초** 동안 재사용된다(15초 폴링에 여러 사용자가 붙어도 Zabbix 에 가볍게 가도록). 그래서 `hosts.*` 의 `collected_at` 은 요청 시각보다 최대 5초 늦을 수 있다.
- `llm_usage_today` 는 [선택] — 필수 단계에서는 `null`.

### #6 `GET /api/problems?severity_min=&hostid=`

Zabbix 실시간 문제(`problem.get`+`trigger.get(selectHosts)`, `libs/zabbix_ro` 경유). 아직 수집되지 않은 문제는 `incident_id: null`.
```json
{
  "data": [
    {
      "eventid": "40211",
      "name": "Disk space is critically low (used > 90%) on C:",
      "severity": { "level": 4, "label": "High" },
      "clock": "2026-10-16T01:20:00Z",
      "host": { "id": "10584", "name": "LAB-PC-07" },
      "tags": [{ "tag": "component", "value": "storage" }],
      "incident_id": 12
    }
  ],
  "meta": { "collected_at": "2026-10-16T01:21:15Z", "truncated": false }
}
```
- 해결된 문제는 목록에 없다. **새 문제가 위**: `clock` 내림차순, 같으면 `eventid` 가 큰 것 먼저.
- 최대 **200건**. 더 있으면 앞 200건만 주고 `meta.truncated: true`.
- `severity_min` 은 0~5, 범위 밖이면 422 `VALIDATION_ERROR`. `hostid` 를 주면 그 호스트의 문제만.
- 호스트를 알 수 없으면 `host: {"id": null, "name": null}` (프론트는 UnknownValue 로 표시). `incident_id` 는 수집 전이거나 shared.db 가 없으면 `null`.
- Zabbix 연결 실패 또는 5초 안에 답이 없으면 503 `ZABBIX_UNAVAILABLE`. 오류 내용·토큰·주소는 응답에 넣지 않는다.

### #10 `GET /api/incidents?status=&severity_min=&limit=&cursor=`

수집된 장애 목록. `started_at` 내림차순(새 장애가 맨 위). 각 항목은 `incident.schema.json` 형식.
```json
{
  "data": [
    {
      "id": 12, "source": "zabbix",
      "zabbix": { "eventid": "40211", "triggerid": "23512", "hostid": "10584" },
      "host": { "id": "10584", "name": "LAB-PC-07" },
      "title": "Disk space is critically low (used > 90%) on C:",
      "severity": { "level": 4, "label": "High" },
      "status": "problem",
      "started_at": "2026-10-16T01:20:00Z", "resolved_at": null,
      "tags": [{ "tag": "component", "value": "storage" }],
      "analysis": { "status": "done", "report_id": 31, "plan_id": 18 }
    }
  ],
  "meta": { "next_cursor": null, "data_as_of": "2026-10-16T01:20:30Z", "stale": false }
}
```
- `status` = `problem | resolved`, `severity_min` 0~5. 잘못된 `cursor` → 422.
- `meta.data_as_of` = 이 목록의 원천인 마지막 수집 성공 시각(#4 의 `scheduler_last_ok` 와 같은 값, 기록이 없으면 `null`). 화면은 "n초 전 갱신"으로 보여 준다.
- `meta.stale` = `true` 면 마지막 수집이 `SCHEDULER_STALE_SEC`(#4 참조)보다 오래됐거나 기록이 없다(= #4 의 `scheduler` 가 `"ok"` 가 아님). 목록 자체는 그대로 내려가며, 화면이 "수집 중단" 배너를 붙인다. 두 필드는 모든 쪽(`cursor` 로 넘긴 다음 쪽 포함)에 들어간다.
- 장애는 `shared.incidents`, `analysis` 는 장애마다 **가장 최근 `kind='analyze'` run** 과 **최신 version 리포트**, 그 리포트의 계획(아래 #11 계획 선택 기준)을 JOIN 해 채운다. `report_id`·`plan_id` 가 없으면 `null`.
- 호스트 보강(Scheduler 의 `trigger.get selectHosts`, FR-SCH-003) 전에는 `host.id`·`host.name`·`zabbix.hostid` 가 `null` 일 수 있다. 프론트는 `UnknownValue` 로 표시한다.

**`analysis.status` 변환 규칙** (`agent-api.md` 3-2, 요청서 확인 요청 4):

| 조건 | `analysis.status` |
|---|---|
| run 없음, `severity < ANALYZE_MIN_SEVERITY`(기본 2) | `skipped` |
| run 없음 | `pending` |
| run `status` ∈ `queued·collecting·analyzing·validating·reported·planning` | `running` |
| run `done` + 최신 리포트 `kind='llm'` | `done` |
| run `done` + 최신 리포트 `kind='fallback'` | `fallback` |
| run `failed` (또는 `done` 인데 리포트가 없음) | `failed` |

### #11 `GET /api/incidents/{id}` — 장애 상세 (데모 핵심)

응답 하나로 장애 상세 화면 전체(리포트·근거·계획·메일 기록)를 그린다.
```json
{
  "data": {
    "incident": { "id": 12, "source": "zabbix", "zabbix": { "eventid": "40211", "triggerid": "23512", "hostid": "10584" },
      "host": { "id": "10584", "name": "LAB-PC-07" }, "title": "Disk space is critically low (used > 90%) on C:",
      "severity": { "level": 4, "label": "High" }, "status": "problem",
      "started_at": "2026-10-16T01:20:00Z", "resolved_at": null,
      "tags": [{ "tag": "component", "value": "storage" }],
      "analysis": { "status": "done", "report_id": 31, "plan_id": 18 } },
    "report": {
      "id": 31, "version": 1, "kind": "llm",
      "summary": "LAB-PC-07의 C: 드라이브 사용률이 96.1%로 임계값(90%)을 넘었습니다.",
      "impact": { "hosts": ["LAB-PC-07"], "services": [], "user_impact": "디스크가 가득 차면 실습 프로그램 저장이 실패할 수 있음", "evidence_ids": ["ev_a1"] },
      "causes": [
        { "rank": 1, "title": "임시 파일 누적", "confidence": "medium", "reasoning": "최근 1시간 사용률이 꾸준히 증가했습니다.", "evidence_ids": ["ev_a1", "ev_a2"], "verify": "임시 폴더 크기 확인" },
        { "rank": 2, "title": "백업 작업으로 인한 일시 증가", "confidence": "low", "reasoning": "백업 작업 여부는 수집되지 않아 판단 근거가 부족합니다.", "evidence_ids": [], "verify": "백업 스케줄 확인" }
      ],
      "facts": [
        { "label": "C: 사용률", "value": 96.1, "unit": "%", "unknown_reason": null, "evidence_ids": ["ev_a1"], "collected_at": "2026-10-16T01:19:30Z" },
        { "label": "메모리 사용률", "value": null, "unit": "%", "unknown_reason": "STALE", "evidence_ids": ["ev_a3"], "collected_at": "2026-10-16T00:40:00Z" }
      ],
      "unknowns": [{ "label": "백업 작업 여부", "reason": "NOT_COLLECTED" }],
      "next_checks": ["임시 폴더 크기와 사용 중인 파일 확인"],
      "created_at": "2026-10-16T01:20:52Z"
    },
    "evidence": [
      { "id": "ev_a1", "tool": "zabbix_get_history", "args": { "itemid": "45123", "time_from": "2026-10-16T00:20:00Z" }, "ok": true, "duration_ms": 412, "result_summary": "최근 1시간 C: 사용률 최대 96.1%", "data_clock": "2026-10-16T01:19:30Z", "called_at": "2026-10-16T01:20:41Z" },
      { "id": "ev_a2", "tool": "zabbix_get_problem", "args": { "eventid": "40211" }, "ok": true, "duration_ms": 236, "result_summary": "트리거 식: C: 사용률 90% 초과, 11분 전 발생", "data_clock": "2026-10-16T01:20:00Z", "called_at": "2026-10-16T01:20:42Z" },
      { "id": "ev_a3", "tool": "zabbix_list_items", "args": { "hostid": "10584", "key_search": "vm.memory" }, "ok": true, "duration_ms": 188, "result_summary": "메모리 값이 40분 전 이후 갱신 안 됨 (stale)", "data_clock": "2026-10-16T00:40:00Z", "called_at": "2026-10-16T01:20:43Z" }
    ],
    "plan": { "id": 18, "title": "LAB-PC-07 C: 드라이브 정리 계획", "goal": "C: 사용률을 90% 아래로", "mode": "preview", "max_tier": "B", "assumptions": ["임시 폴더 파일은 업무 데이터가 아님"] },
    "steps": [
      { "seq": 1, "action_id": "check_disk_usage", "title": "디스크 사용량 확인", "target": "LAB-PC-07 C:", "command_preview": "Get-PSDrive C", "tier": "A", "rationale": "규칙: packs/it/actions.yaml check_disk_usage", "precheck": null, "expected_effect": "현재 사용량 확인", "risk": "없음 (조회)", "rollback": null, "evidence_ids": ["ev_a1"] },
      { "seq": 2, "action_id": "clean_temp_files", "title": "임시 파일 정리", "target": "LAB-PC-07 %TEMP%", "command_preview": "Move-Item $env:TEMP\\* (Join-Path $env:TEMP ..\\dejafix-quarantine)", "tier": "B", "rationale": "규칙: packs/it/actions.yaml clean_temp_files", "precheck": "임시 폴더 크기와 사용 중인 파일 확인", "expected_effect": "수 GB 확보 예상", "risk": "사용 중인 파일 이동 시 프로그램 오류 가능", "rollback": "격리 폴더의 파일을 원래 위치로 다시 이동", "evidence_ids": ["ev_a1"] },
      { "seq": 3, "action_id": "reboot_host", "title": "서버 재부팅", "target": "LAB-PC-07", "command_preview": "Restart-Computer", "tier": "C", "rationale": "규칙: packs/it/actions.yaml reboot_host", "precheck": null, "expected_effect": null, "risk": "모든 서비스 중단", "rollback": null, "evidence_ids": [] }
    ],
    "mail_logs": [
      { "id": 7, "kind": "incident_report", "recipient": "oncall@example.com", "status": "sent", "attempts": 1, "error": null, "created_at": "2026-10-16T01:20:55Z", "sent_at": "2026-10-16T01:20:58Z" }
    ]
  },
  "meta": {}
}
```
- 출처: `shared.incidents`·최신 version `analysis_reports`·그 리포트의 run 의 `tool_calls`·그 리포트의 `change_plans`·`plan_steps`(읽기 전용 ATTACH) + `backend.db` `mail_logs`. Backend 는 **저장된 값을 옮기기만** 한다 — 분석 문장·원인·티어를 만들거나 바꾸지 않는다.
- **계획 선택 기준**: `change_plans.report_id = 응답에 쓴 report.id` 인 계획을 쓴다(같은 리포트에 여러 개면 가장 최근 `id`). 그런 계획이 없을 때만 그 장애의 최신 계획을 쓴다. 다시 분석해 리포트 version 이 올라가도 리포트와 계획이 어긋나지 않게 하기 위함이다.
- **리포트가 아직 없으면** `report: null, evidence: [], plan: null, steps: []`. 프론트는 `incident.analysis.status` 로 "분석 중" 등을 표시한다. 메일 기록이 없으면 `mail_logs: []`.
- `report.causes[].evidence_ids` 의 모든 ID 는 `evidence[]` 에 존재한다(값은 Agent 가 검증해 저장한다). `report.kind="fallback"` 이면 프론트가 "LLM 미연결 — 규칙 기반 최소 리포트" 라벨을 붙인다.
- `evidence` 는 리포트가 참조하는 run 의 `tool_calls` 전체이고 **`result_json` 은 제외**한다.
- `steps[].tier` 는 코드가 `actions.yaml` 로 판정한 값만이다(LLM 원본 티어 없음). `causes[].confidence` 는 `low|medium|high` 문자만(퍼센트·점수 금지).
- `incident.severity.label`: 0 `Not classified` · 1 `Information` · 2 `Warning` · 3 `Average` · 4 `High` · 5 `Disaster`.
- 404 `NOT_FOUND`: 없는 장애.

### #18 `POST /api/chat` (SSE)

요청 (장애 상세에서 열면 `incident_id` 자동 첨부, 새 대화는 `conversation_id` 생략)
```json
{ "conversation_id": "c_7f3a", "message": "이 서버 백업 작업이 원인인가?", "context": { "incident_id": 12, "hostid": "10584" } }
```
- Backend 는 Agent `POST /v1/chat` 에 `caller:"backend"`, 헤더 `X-User-Id`·`X-User-Role` 을 붙여 호출하고 **이벤트를 바꾸지 않고 그대로 중계**한다(`agent-api.md` 1-2). operator 미만은 403 `FORBIDDEN`. `message` 가 비었거나 공백뿐이거나 **4000자를 넘으면** Agent 로 보내지 않고 422 `VALIDATION_ERROR`.
- 응답 `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- 이벤트 6종과 순서: `meta`(항상 첫 이벤트) → (`tool_call` → `tool_result`)* → `token`* → `final` | `error`. 규칙 기반 답변은 `meta` → `final` 만 와도 정상.
```
event: meta
data: {"conversation_id":"c_7f3a","run_id":"r_91b2","message_id":101}

event: token
data: {"text":"백업 작업 여부는 "}

event: final
data: {"message_id":102,"content":"...","evidence_ids":["ev_b1"],"unknowns":[{"label":"백업 작업 여부","reason":"NOT_COLLECTED"}]}
```
- Agent 에 연결할 수 없거나 요청 후 3초 안에 첫 이벤트가 없으면 Backend 가 `event: error` + `{"code":"AGENT_UNAVAILABLE"}` 를 보내고 닫는다. 스트림 중간에 끊겨도 같다.
- Agent 가 15초(`CHAT_KEEPALIVE_SEC`) 넘게 조용하면(도구 호출·LLM 대기) Backend 가 `: ping` **SSE 주석 줄**을 보내 nginx·프록시가 유휴 연결을 끊지 않게 한다. 이벤트가 아니므로 클라이언트는 무시한다. 이벤트 도중에는 끼워 넣지 않는다.
- **비스트리밍(탈출 규칙 1)**: 같은 경로가 JSON 으로 응답한다(Agent 는 그대로 스트림을 보내고 Backend 가 합친다). 프론트는 응답 `Content-Type` 으로 SSE/JSON 을 고른다.
```json
{
  "data": {
    "conversation_id": "c_7f3a", "message_id": 102,
    "content": "백업 작업 여부는 수집되지 않아 확인할 수 없습니다.",
    "evidence_ids": ["ev_b1"],
    "unknowns": [{ "label": "백업 작업 여부", "reason": "NOT_COLLECTED" }],
    "tool_calls": [{ "id": "ev_b1", "tool": "zabbix_get_history", "args": { "itemid": "45123" }, "ok": true, "duration_ms": 412, "summary": "최근 1시간 C: 사용률 최대 96.1%", "data_clock": "2026-10-16T01:24:30Z" }]
  },
  "meta": {}
}
```
- `error` 이벤트가 오면 HTTP 502 + `{"error":{"code":<error.code>,"message":...}}`.

## 4. 요청서 5장 "백엔드 확인 요청" 8건 — 처리 (Issue #23, 8건 모두 수락)

| # | 안건 | 이 계약의 처리 |
|---|---|---|
| 1 | severity 형식 | #6·#10·#11 모두 `{level, label}` |
| 2 | #4 상태 값 | `"ok" \| "down"`, `shared_db` 만 `"waiting"` 추가, `scheduler_last_ok` 없으면 `null` |
| 3 | #5 "오늘" 기준 | KST 자정. `hosts` 하위 3개는 각각 `Measured` |
| 4 | `analysis.status` 변환 | #10 의 변환표 (`agent-api.md` 3-2 와 동일) |
| 5 | 오류 코드 추가 | `UNAUTHORIZED`·`FORBIDDEN`·`NOT_FOUND`·`AGENT_UNAVAILABLE` 등록. 추가 제안: `VALIDATION_ERROR`(422), `SHARED_DB_UNAVAILABLE`(503), `INTERNAL_ERROR`(500) |
| 6 | #18 비스트리밍 응답 | `conversation_id`·`message_id` 포함 |
| 7 | #1 토큰 만료 | `meta.expires_at` 필드 제공. 만료 시간은 **8시간**(`JWT_EXPIRE_MIN` 기본 480분, 데모 중 끊기지 않게 — #23 권장) |
| 8 | #11 리포트 없을 때 | `report: null, evidence: [], plan: null, steps: []` |

### 요청서 예시와 다른 점

- 요청서 #11 예시의 `causes[0].evidence_ids` 가 `ev_a2` 를 가리키지만 `evidence[]` 에 없었다. 이 계약은 "모든 evidence_ids 가 evidence[] 에 존재" 규칙에 맞게 `ev_a2` 항목을 추가했다.
- 프론트 권한표(viewer 도 AI 질문 가능, 요청서 F17)와 달리 **#18 은 operator** 다(`FR-BE-003`). viewer 에게 열려면 이 계약을 먼저 바꾼다.
- 요청서 #11 예시의 3단계(서버 재부팅)는 `action_id: null`·"미등록 → C"였지만, `packs/it/actions.yaml` 에 `reboot_host` 가 C 등급으로 등록돼 있어 실제 Agent 출력처럼 `action_id: "reboot_host"`·`rationale: "규칙: packs/it/actions.yaml reboot_host"` 로 바꿨다. 참고로 미등록 동작이면 Agent 는 `rationale` 을 `packs/it/actions.yaml 미등록 동작(<id 또는 제목>) → C (SAFE-06)` 형식으로 쓴다.
- `host.id`·`host.name`·`zabbix.hostid` 는 `null` 을 허용한다(호스트 보강 전, PR #45 리뷰 반영).

## 5. 변경 절차

- 계약 변경은 **계약 PR → 구현 PR** 순서, 2인 승인. 이 파일을 바꾸면 `docs/plan.md` 7장의 해당 줄도 같은 PR 에서 고친다.
- FastAPI OpenAPI(`/docs`)와 프론트 MSW 가 이 문서와 일치해야 한다(FR-INF-008).

## 6. 확장 엔드포인트 — 총괄(orchestrator) 읽기 중계 [선택]

DejaFix 장애 대응에서 부서 에이전트들이 한 일을 모아 두는 **총괄 에이전트**의 기록을 관리자 화면(`/admin/orchestrator`)에서 본다.
필수 8개와 별개의 [선택] 확장이고, 2장 표와 필수 8개 테스트에는 들어가지 않는다.

| # | 메서드·경로 | 최소 역할 | 데이터 출처 |
|---|---|---|---|
| 26 | `GET /api/orchestrator/incidents` | admin | 총괄 `GET /api/incidents` 읽기 중계 |
| 27 | `GET /api/orchestrator/departments` | admin | 총괄 `GET /api/departments` 읽기 중계 |

공통 규칙
- **읽기 전용**: Backend 가 총괄로 보내는 요청은 위 두 GET 뿐이다. 승인·장애 주입 같은 쓰기 경로는 중계하지 않고, 화면에도 실행·승인 버튼이 없다(SAFE-04).
- **그대로 중계**: 분석·원인·티어·문장을 만들거나 바꾸지 않는다. 단계(`steps[]`)의 결과 본문 `output`만 뺀다.
- 총괄 주소는 `ORCHESTRATOR_URL`(비어 있으면 연결 안 됨). 총괄이 없거나 5초 안에 정상 응답하지 않으면 **503 `ORCHESTRATOR_UNAVAILABLE`** 이고, 화면은 "확인할 수 없음"으로 그린다(지어낸 값 금지, SAFE-08).
- 봉투는 필수 API 와 같다: `{data, meta}`. `meta.source` 는 항상 `"orchestrator"`, `meta.mock` 은 총괄이 목 모드인지.

### #26 `GET /api/orchestrator/incidents`
`data` = 사건 배열(오래된 것부터). 한 사건:
```json
{
  "context_id": "ctx_inc_ab12cd34ef56", "kind": "scenario_a", "title": "payment 장애 감지 (error_rate_5xx)",
  "component": "payment", "status": "open | resolved | degraded",
  "opened_at": "2026-10-23T01:00:00Z", "closed_at": "2026-10-23T01:00:05Z",
  "steps": [{"step_id": "diagnose", "skill": "diagnose_incident", "label": "원인 진단 (infra)", "dept": "infra",
             "status": "pending | running | completed | failed | held | skipped | rejected_by_human | transfer_queued",
             "attempts": 1, "note": "", "grade": "read | A | B | C", "started_at": "...", "finished_at": "...",
             "transferred_to": null, "reason_code": null}],
  "events": [{"at": "...", "message": "사건 시작: ..."}],
  "summary": ["원인 진단 (infra) [infra] 완료"],
  "metrics": {"mttr_seconds": 4.2, "steps_total": 12, "steps_completed": 12, "held": 0, "transfers": 0, "retries": 0, "auto_rate": 1.0},
  "pending_holds": [{"step_id": "rollback", "skill": "rollback_deployment", "label": "원인 배포 롤백 (B)"}]
}
```

### #27 `GET /api/orchestrator/departments`
`data` = 부서 배열. `meta` 에 `window_seconds`(그래프 구간, 600)·`bucket_seconds`(30).
```json
{
  "name": "marketing", "owner": "재헌", "mode": "mock | real", "available": true, "unavailable_reason": null,
  "skills": [{"id": "publish_notice", "grade": "A", "priority": "required", "orchestrator": true,
              "calls": 5, "errors": 1, "success_rate": 0.8, "avg_ms": 702, "retries": 1,
              "series": [{"t": "...", "calls": 0, "errors": 0, "avg_ms": null}]}],
  "usage": {"calls": 9, "errors": 1, "waiting": 0, "success_rate": 0.889, "avg_ms": 702, "p95_ms": 716, "retries": 1, "last_called_at": "..."},
  "series": [{"t": "...", "calls": 0, "errors": 0, "avg_ms": null}],
  "recent": [{"at": "...", "skill": "publish_notice", "status": "completed", "outcome": null, "duration_ms": 703, "context_id": "ctx_inc_..."}]
}
```
사용량은 **총괄이 그 부서를 부른 호출을 센 실측**이다. 호출이 없으면 `success_rate`·`avg_ms` 는 `null`(0 으로 지어내지 않는다). 부서 내부의 CPU·메모리는 알 수 없어 없다.
