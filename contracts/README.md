# contracts — 파트 간 유일한 약속

코드·문서가 다르면 **여기가 우선**이다(루트 CLAUDE.md 0·④). 변경은 **계약 PR → 구현 PR** 순서, 계약 PR은 **2인 승인**(소유자 + 소비자 파트 1명). 계약을 바꾼 PR에서 `docs/plan.md`의 해당 절도 함께 고친다. Claude Code는 이 폴더를 직접 편집하지 않는다(`.claude/hooks/guard-protected.mjs`) — 사람이 쓴다.

## 파일·소유자 (기획서 10-1, 요구사항 FR-INF-008)

| 파일 | 내용 | 원본 절 | 소유자 | 소비자(승인 1명) | 상태 |
|---|---|---|---|---|---|
| `api.md` | Backend REST — 필수 8개(#1·3·4·5·6·10·11·18) 상세, 나머지 planned. 공통 봉투 `{data, meta}`/`{error}`, `Measured`, 커서, `analysis.status` 6값, 채팅은 `fetch` 스트림 | 기획서 7-1, SRS 6-2 | Backend 담당 | 연동·인프라 담당 | v0 작성 중 |
| `incident.schema.json` | 표준 Incident 형식 `id, source, zabbix{eventid,triggerid,hostid}, host{id,name}, title, severity{level,label}, status, started_at, resolved_at, tags[], analysis{status,report_id,plan_id}` | 기획서 5-5, SRS DR-018 | Backend 담당 | 연동·인프라 담당·DB·메일 담당 | v0 작성 중 |
| `agent-api.md` | Backend ↔ Agent: `/healthz`, `/v1/chat` SSE 이벤트(`meta/tool_call/tool_result/token/final/error`), 리포트·계획 초안 JSON Schema, `unknown_reason` 변환표 | 기획서 7-2, SRS 6-3 | DB·메일 담당(초안) → 팀장(10/15 13:00부터) | Backend 담당 | v0 작성 중 |
| `mcp-tools.md` | Agent ↔ MCP 도구 12개(필수 5 상세, 7 planned·서버 미등록), 공통 봉투, Zabbix 매핑 | 기획서 7-3, SRS 6-4 | Zabbix·MCP 담당 | 팀장(Agent) | v0 작성 중 |
| `db-schema.sql` | SQLite DDL — 필수 11 테이블(shared 9 + backend 2), 전 문장 `IF NOT EXISTS`, CHECK(`mode='preview'`, 티어, 상태값), 인덱스 | 기획서 5-2·5-3, SRS 7장 | DB·메일 담당 | Backend 담당·팀장(Agent) | v0 작성 중 |

- 입력: 노션 **프론트 API 요청서**(화면 담당·연동·인프라 담당)와 **자빅스 API 목록**(Zabbix·MCP 담당·팀장) → 백엔드가 두 문서를 받아 `api.md`·`mcp-tools.md`를 확정 → 프론트가 명세서로 연동(멘토 순서 ①→②→③→④, FR-INF-014). 요청서 항목과의 대응표는 PR 본문에.
- v0 승인 `(TODO: 추후결정 — 후보: 기획서 5~7장 + 노션 문서 2개)`. 머지 전에는 기획서 5~7장을 임시 계약으로 쓴다.
- 완료 판정: 5파일 dev 머지, FastAPI OpenAPI·프론트 MSW가 `api.md`와 일치(FR-INF-008 T).
- 스키마 변경 정책: MVP 중 `ALTER` 금지, 바뀌면 개발 DB 재생성(NFR-MAINT-009).
