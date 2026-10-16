# Backend ↔ Agent 계약 v0 (`contracts/agent-api.md`)

- 소유자: DB·메일 담당(초안) → 팀장(10/15 13:00 인계 후) / 승인: Backend 담당
- 원본: `docs/plan.md` 4-5·7-2, `docs/requirements.md` IF-INT-AG-001~005·IF-INT-MCP-001·FR-AG-002~014, 노션 「DejaFix 프론트 API 요청서」 #18
- 함께 보는 계약: `db-schema.sql`(저장 형식), `api.md`(Backend가 프론트에 주는 형식), `mcp-tools.md`(근거가 되는 도구)
- 범위: [필수]는 1장 `GET /healthz`, `POST /v1/chat`과 2장 리포트·계획 JSON 형식. 나머지는 표에 등급을 적었다.

## 0. 공통

| 항목 | 값 |
|---|---|
| 주소 | `AGENT_URL` (compose 기본 `http://agent:8100`, 로컬 `http://localhost:8100`). 내부 전용, 외부 공개 없음 |
| 호출 방향 | Backend → Agent만. Agent는 Backend를 부르지 않는다 |
| 사용자 전달 | 헤더 `X-User-Id`(backend.db `users.id`), `X-User-Role`(`admin`·`operator`·`viewer`). Agent는 인증하지 않고 기록만 한다 |
| 호출자 | 본문 `caller`. Backend는 항상 `"backend"`. `agent_runs.caller`에 저장 (FR-AG-014) |
| 내부 토큰 | 헤더 `X-Internal-Token` = `.env` `INTERNAL_TOKEN`. **[선택]**: 값이 비어 있으면 검사하지 않는다. 검사할 때 불일치는 `401` (NFR-SEC-003) |
| 본문·시각 | JSON UTF-8. 시각은 UTC ISO8601 `2026-10-16T01:20:00Z` |
| 스트림 밖 오류 | `{"error": {"code": "...", "message": "..."}}` + HTTP 상태 (Backend `api.md`와 같은 봉투) |

| 메서드·경로 | 등급 | 요약 |
|---|---|---|
| `GET /healthz` | [필수] | 상태 확인 |
| `POST /v1/chat` | [필수] | 채팅, SSE |
| `POST /v1/incidents/{id}/analyze` | [선택] | 다시 분석, `202 {run_id}` |
| `GET /v1/runs/{run_id}` | [선택] | 런 상태 |
| `POST /v1/incidents/{id}/plans` | [이후] | 계획 단독 생성 |

분석 자체는 API가 아니라 **분석 워커**가 한다. 워커는 10초마다 `shared.db`에서 리포트 없는 장애(`severity ≥ ANALYZE_MIN_SEVERITY`)를 찾아 분석하고 결과를 `agent_runs`·`tool_calls`·`analysis_reports`·`change_plans`·`plan_steps`에 저장한다(`caller='worker'`). Backend는 그 테이블을 읽기만 한다.

## 1. [필수] 엔드포인트

### 1-1. `GET /healthz`

응답 `200`
```json
{ "ok": true, "model": null, "mcp": { "zabbix": "ok" } }
```
- `model`: 실제로 부를 LLM 모델 이름. LLM 미설정(fallback 모드)이면 `null`, 가짜 LLM이면 `"fake"`.
- `mcp.zabbix`: `"ok"` | `"down"`. MCP가 죽어도 `200`으로 상태만 알린다.
- 기동 시 MCP `tools/list`에 허용 목록 밖 도구가 있으면 Agent는 **기동하지 않는다**(FR-AG-010, SAFE-03). 그러면 `/healthz` 자체가 응답하지 않고, Backend `GET /api/health`는 `agent: "down"`을 낸다.

### 1-2. `POST /v1/chat`

요청
```json
{
  "conversation_id": "c_7f3a",
  "message": "이 서버 백업 작업이 원인인가?",
  "context": { "incident_id": 12, "hostid": "10584" },
  "caller": "backend"
}
```
- `conversation_id`: 새 대화면 생략. 없는 ID이거나 다른 사용자의 대화면 스트림을 열기 전에 `404 {"error":{"code":"CONVERSATION_NOT_FOUND"}}` (대화는 본인 것만, 기획서 G11).
- `context`: 둘 다 선택. `incident_id`가 있으면 그 장애와 최신 리포트 요약을 프롬프트에 데이터로 첨부하고 `conversations.incident_id`에 저장(FR-AG-011).
- `message`가 비어 있으면 `400 {"error":{"code":"BAD_REQUEST"}}`.

응답 `200`, `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`

이벤트 6종. 한 이벤트는 `event:` 줄 + `data:` 한 줄(JSON 한 줄) + 빈 줄.
```
event: meta
data: {"conversation_id":"c_7f3a","run_id":"r_91b2","message_id":101}

event: tool_call
data: {"id":"ev_b1","tool":"zabbix_get_history","args":{"itemid":"45123","time_from":"2026-10-16T00:25:00Z"},"started_at":"2026-10-16T01:25:02Z"}

event: tool_result
data: {"id":"ev_b1","ok":true,"duration_ms":412,"summary":"최근 1시간 CPU 사용률 최대 96.1%","data_clock":"2026-10-16T01:24:30Z"}

event: token
data: {"text":"백업 작업 여부는 "}

event: final
data: {"message_id":102,"content":"백업 작업 여부는 수집되지 않아 확인할 수 없습니다. 최근 1시간 CPU 사용률은 최대 96.1%입니다.","evidence_ids":["ev_b1"],"unknowns":[{"label":"백업 작업 여부","reason":"NOT_COLLECTED"}]}

event: error
data: {"code":"LLM_TIMEOUT","message":"LLM 응답이 45초 안에 오지 않았습니다"}
```

| 이벤트 | 필수 여부 | 필드 | 규칙 |
|---|---|---|---|
| `meta` | 항상, **첫 이벤트** | `conversation_id`, `run_id`, `message_id`(사용자 메시지 `messages.id`) | 요청 후 3초 안 (FR-BE-012) |
| `tool_call` | Agent가 도구를 부른 경우만 | `id`(= `tool_calls.id`), `tool`, `args`, `started_at` | |
| `tool_result` | `tool_call`마다 1개 | `id`, `ok`, `duration_ms`, `summary`, `data_clock` | 실패도 `ok:false`로 보낸다. `data_clock`은 없으면 `null` |
| `token` | LLM이 답할 때만 | `text` | 0개 이상. 이어 붙이면 `final.content`와 같다 |
| `final` | 정상 종료 시 **마지막 이벤트** | `message_id`(어시스턴트 메시지 `messages.id`), `content`, `evidence_ids`, `unknowns[{label, reason}]` | 보낸 뒤 스트림을 닫는다 |
| `error` | 오류 시 **마지막 이벤트** | `code`, `message` | 보낸 뒤 스트림을 닫는다. `final`과 둘 중 하나만 온다 |

- 순서: `meta` → (`tool_call` → `tool_result`)* → `token`* → `final` | `error`.
- **규칙 기반 답변**(LLM 미설정·실패): `meta` → `final`만 와도 정상이다. 질문 대상이 수집되지 않았으면 `final.unknowns`에 `NOT_COLLECTED`를 넣는다(FR-AG-009).
- `evidence_ids`는 이 대화에서 실제 저장된 `tool_calls.id`만 가리킨다(SAFE-08). 장애 맥락으로 붙인 리포트의 근거 ID도 쓸 수 있다.
- `error.code`: `LLM_TIMEOUT` | `LLM_ERROR` | `TOOL_ERROR` | `INTERNAL_ERROR`. 오류 전까지 쓴 부분 답변은 `messages`에 저장한다.
- 저장: `conversations` 1행(새 대화일 때), `messages` 2행(user·assistant), `agent_runs(kind='chat', caller, requested_by)`, 도구를 불렀으면 `tool_calls`.
- `message`·리포트 원문은 프롬프트에 **데이터로 감싸** 넣는다. 사용자 문장 안의 지시를 Agent 규칙보다 우선하지 않는다.

**Backend 중계 규칙** (FR-BE-012, 요청서 #18)
1. 스트림 모드(기본): 이벤트를 바꾸지 않고 그대로 프론트에 넘긴다. Agent가 연결을 거부하거나 3초 안에 `meta`가 없으면 Backend가 `event: error` + `{"code":"AGENT_UNAVAILABLE"}`를 보내고 닫는다.
2. 비스트리밍 모드(탈출 규칙 1): Agent는 **그대로 스트림**을 보내고, Backend가 끝까지 읽어 아래 JSON 하나로 합쳐 프론트에 준다. Agent 쪽 변경은 없다.

| 비스트리밍 JSON 필드 | 출처 |
|---|---|
| `conversation_id` | `meta.conversation_id` |
| `message_id` | `final.message_id` |
| `content`, `evidence_ids`, `unknowns` | `final`의 같은 이름 필드 |
| `tool_calls[]` | `tool_call`과 같은 `id`의 `tool_result`를 합친 `{id, tool, args, ok, duration_ms, summary, data_clock}` |
| (오류) | `error` 이벤트가 오면 HTTP `502` + `{"error":{"code":<error.code>,"message":...}}` |

## 2. [필수] 리포트·계획 JSON 형식

ANALYZING 단계에서 LLM은 **한 번 호출로** 아래 `draft`를 JSON으로만 답한다(FR-AG-004). VALIDATING·PLANNING을 거친 결과가 `db-schema.sql`의 `analysis_reports`·`change_plans`·`plan_steps`에 저장되고, Backend `#11`이 그 값을 그대로 응답한다. fallback 경로도 **같은 형식**으로 저장한다(`kind='fallback'`).

### 2-1. LLM 초안 스키마 (JSON Schema, draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "dejafix/agent/analysis-draft-v0",
  "type": "object",
  "required": ["report", "plan"],
  "additionalProperties": false,
  "$defs": {
    "evidence_ids": { "type": "array", "items": { "type": "string", "pattern": "^ev_" } },
    "unknown_reason": { "enum": ["NO_DATA", "STALE", "TOOL_ERROR", "NO_PERMISSION", "NOT_COLLECTED"] }
  },
  "properties": {
    "report": {
      "type": "object",
      "required": ["summary", "impact", "causes", "facts", "unknowns", "next_checks"],
      "additionalProperties": false,
      "properties": {
        "summary": { "type": "string", "minLength": 1 },
        "impact": {
          "type": "object",
          "required": ["hosts", "services", "user_impact", "evidence_ids"],
          "additionalProperties": false,
          "properties": {
            "hosts": { "type": "array", "items": { "type": "string" } },
            "services": { "type": "array", "items": { "type": "string" } },
            "user_impact": { "type": ["string", "null"] },
            "evidence_ids": { "$ref": "#/$defs/evidence_ids" }
          }
        },
        "causes": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["rank", "title", "confidence", "reasoning", "evidence_ids", "verify"],
            "additionalProperties": false,
            "properties": {
              "rank": { "type": "integer", "minimum": 1 },
              "title": { "type": "string" },
              "confidence": { "enum": ["low", "medium", "high"] },
              "reasoning": { "type": "string" },
              "evidence_ids": { "$ref": "#/$defs/evidence_ids" },
              "verify": { "type": "string" }
            }
          }
        },
        "facts": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["label", "value", "unit", "unknown_reason", "evidence_ids", "collected_at"],
            "additionalProperties": false,
            "properties": {
              "label": { "type": "string" },
              "value": { "type": ["number", "string", "null"] },
              "unit": { "type": ["string", "null"] },
              "unknown_reason": { "oneOf": [{ "type": "null" }, { "$ref": "#/$defs/unknown_reason" }] },
              "evidence_ids": { "$ref": "#/$defs/evidence_ids" },
              "collected_at": { "type": ["string", "null"] }
            }
          }
        },
        "unknowns": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["label", "reason"],
            "additionalProperties": false,
            "properties": {
              "label": { "type": "string" },
              "reason": { "$ref": "#/$defs/unknown_reason" }
            }
          }
        },
        "next_checks": { "type": "array", "items": { "type": "string" } }
      }
    },
    "plan": {
      "type": ["object", "null"],
      "required": ["title", "goal", "assumptions", "steps"],
      "additionalProperties": false,
      "properties": {
        "title": { "type": "string" },
        "goal": { "type": ["string", "null"] },
        "assumptions": { "type": "array", "items": { "type": "string" } },
        "steps": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "required": ["title"],
            "additionalProperties": false,
            "properties": {
              "action_id": { "type": ["string", "null"] },
              "title": { "type": "string" },
              "target": { "type": ["string", "null"] },
              "command_preview": { "type": ["string", "null"] },
              "tier": { "description": "LLM이 적어도 무시한다. 티어는 PLANNING 코드가 정한다" },
              "rationale": { "type": ["string", "null"] },
              "precheck": { "type": ["string", "null"] },
              "expected_effect": { "type": ["string", "null"] },
              "risk": { "type": ["string", "null"] },
              "rollback": { "type": ["string", "null"] },
              "evidence_ids": { "$ref": "#/$defs/evidence_ids" }
            }
          }
        }
      }
    }
  }
}
```

- `confidence`는 `low|medium|high` 문자만. `"87%"` 같은 값은 스키마에서 거부된다(SAFE-11).
- 원인 개수는 스키마로 막지 않는다. 3개를 넘으면 VALIDATING이 `rank` 순으로 **잘라** 3개만 저장한다(FR-AG-005 ④).
- `action_id`는 프롬프트에 준 활성 팩 `actions.yaml`의 동작 ID 중 하나. 맞는 동작이 없으면 생략한다(FR-AG-004 [v1.3]).

### 2-2. 검증·확정 규칙 (VALIDATING → PLANNING, 코드만)

| 단계 | 규칙 | 근거 |
|---|---|---|
| 스키마 | 2-1 통과 못 하면 LLM 실패로 보고 fallback 경로 | FR-AG-005 ①, FR-AG-007 |
| 근거 | `facts[]`에서 `value`가 null이 아니면 `evidence_ids`가 비어 있지 않고 전부 이 run의 `tool_calls.id`에 있어야 한다. 아니면 `value=null` + `unknown_reason`(근거 ID가 없으면 `NOT_COLLECTED`)으로 바꾼다. `causes[]`·`impact`·`steps[]`의 `evidence_ids`에서 실제로 없는 ID는 지운다. 그 결과 근거가 빈 원인은 `confidence="low"`로 둔다(요청서 #11 예시의 2순위 원인과 같음) | SAFE-08, FR-AG-005 ②③ |
| 오래된 값 | 근거 도구 결과가 `stale:true`이면 그 값은 `null` + `STALE` | SAFE-09 |
| 티어 | 각 단계를 `actions.yaml`로 매칭해 코드가 `tier`를 정한다. LLM의 `tier`는 버린다. 미등록·`action_id` 없음 → `C`. `B`인데 `precheck`·`rollback` 중 하나라도 없으면 `C`로 강등하고 `rationale`에 사유 | SAFE-06·07, FR-AG-006 |
| 최고 티어 | `change_plans.max_tier` = 단계 티어의 최댓값(C > B > A) | DR-007 |
| 계획 실패 | `plan`이 `null`이거나 PLANNING이 실패하면 리포트만 저장하고 `agent_runs.error`에 `PLAN_FAILED: <사유>` | FR-AG-008 |

### 2-3. 저장 후 형식 (= Backend `#11`이 읽는 값)

- `report` → `analysis_reports` 한 행. `impact`·`causes`·`facts`·`unknowns`·`next_checks`는 같은 이름 + `_json` 컬럼에 JSON으로. `id`·`version`·`kind`·`created_at`은 Agent가 채운다.
- `plan` → `change_plans` 한 행(`mode`는 항상 `'preview'`) + `steps` → `plan_steps` 여러 행(`seq`는 1부터, `evidence_ids` → `evidence_ids_json`).
- 근거 → `tool_calls`. Backend는 `result_json`을 응답에 넣지 않는다.
- 저장된 값은 바꾸지 않는다. 다시 분석하면 `version`이 +1인 새 리포트·새 계획을 만든다.

## 3. 상태 값

### 3-1. `agent_runs.status` (Agent가 씀)

`queued` → `collecting` → `analyzing` → `validating` → `reported` → `planning` → `done`, 실패 시 `failed`.
- LLM 미설정·실패·타임아웃·예산 초과는 **`failed`가 아니다**. fallback 리포트·계획을 저장하고 `done`으로 끝내며 `error`에 `LLM_NOT_CONFIGURED`·`LLM_TIMEOUT`·`LLM_ERROR`·`LLM_BUDGET` 중 하나를 남긴다(FR-AG-002).
- `failed`는 리포트를 하나도 저장하지 못한 경우만.

### 3-2. 화면 `analysis.status` 6값으로 바꾸는 규칙 (Backend가 계산, 확정은 `api.md`)

Backend가 장애마다 **가장 최근 `kind='analyze'` run**과 최신 리포트를 보고 정한다. 아래는 요청서 확인 요청 4번의 제안을 이 계약의 상태 값에 맞춘 것이다.

| 조건 | `analysis.status` |
|---|---|
| run 없음, `severity < ANALYZE_MIN_SEVERITY` | `skipped` |
| run 없음 (워커가 아직 안 집음) | `pending` |
| run `status` ∈ `queued`·`collecting`·`analyzing`·`validating`·`reported`·`planning` | `running` |
| run `done` + 최신 리포트 `kind='llm'` | `done` |
| run `done` + 최신 리포트 `kind='fallback'` | `fallback` |
| run `failed` | `failed` |

## 4. `unknown_reason` 코드와 MCP 오류 변환표 (IF-INT-MCP-001, AS-M13)

| 코드 | 뜻 | 화면 문구 예 |
|---|---|---|
| `NO_DATA` | 조회했지만 값이 없음 | 확인할 수 없음 · 데이터 없음 |
| `STALE` | 마지막 값이 `max(주기×3, 10분)`보다 오래됨 | 확인할 수 없음 · 오래된 값 |
| `TOOL_ERROR` | 도구·Zabbix 오류, 타임아웃 | 확인할 수 없음 · 조회 실패 |
| `NO_PERMISSION` | 읽기 전용 계정에 권한 없음 | 확인할 수 없음 · 권한 없음 |
| `NOT_COLLECTED` | 고정 수집 세트에 없는 항목 | 확인할 수 없음 · 수집하지 않음 |

| MCP 결과 | → `unknown_reason` |
|---|---|
| `{ok:false, reason:"NO_PERMISSION"}` | `NO_PERMISSION` |
| `{ok:false, reason:"NOT_FOUND"}` | `NO_DATA` |
| `{ok:false, reason:"ZABBIX_ERROR"}`, 타임아웃 | `TOOL_ERROR` |
| `{ok:true}` + 빈 결과 | `NO_DATA` |
| 값에 `stale:true` | `STALE` |
| 고정 수집 세트에 없는 항목을 물음 | `NOT_COLLECTED` |

## 5. [선택]·[이후] 엔드포인트 (필수 완료 후)

| 메서드·경로 | 요청 | 응답 |
|---|---|---|
| `POST /v1/incidents/{id}/analyze` [선택] | `{"force": false}` | `202 {"run_id":"r_..."}`. 같은 장애에 진행 중인 run이 있으면 그 `run_id`. `caller`는 본문의 값 |
| `GET /v1/runs/{run_id}` [선택] | — | `200 {"status":"running", "report_id":null, "plan_id":null, "error":null}` (`status`는 3-1 값) |
| `POST /v1/incidents/{id}/plans` [이후] | `{"goal": "..."}` | `202 {"run_id":"r_..."}` |

## 6. 변경 절차

- 이 파일을 바꾸면 **계약 PR → 구현 PR** 순서, 2인 승인(소유자 + Backend 담당). `docs/plan.md` 7-2의 해당 줄도 같은 PR에서 고친다.
- 이벤트 이름·필드 이름을 바꾸면 Backend 중계와 프론트 파서가 같이 깨진다. 필드 추가는 뒤에 붙이고, 이름 변경·삭제는 하지 않는다.
