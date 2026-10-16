# PLAN-mcp-zabbix — Zabbix MCP 서버 작업 큐 (담당 Zabbix·MCP 담당, 부 DB·메일 담당 / 폴더 `mcp-zabbix/`)

- 기준: `mcp-zabbix/CLAUDE.md`, `docs/mvp-checklist.md` "mcp-zabbix", `contracts/mcp-tools.md`(Zabbix·MCP 담당 소유, 머지 전엔 기획서 7-3), `libs/zabbix_ro/CLAUDE.md`
- 항목마다 `uv run ruff check . && uv run ruff format --check . && uv run pytest` 통과 후 커밋 1개. 실패 2번이면 `[BLOCKED]` + `LOG-mcp-zabbix.md`
- 개발 기본 `ZABBIX_MOCK=true`. 야간에는 실 Zabbix 호출 금지. `libs/zabbix_ro`가 아직 없으면 같은 인터페이스의 임시 목 클라이언트를 `mcp-zabbix/` 안에 두고 LOG에 적는다(머지 때 교체)

## 작업 큐
- [x] **1. 서버 골격** (FR-MCP-001, FR-INF-002): Python MCP SDK, streamable HTTP `:8200/mcp`, `GET /healthz`, 설정(`ZABBIX_*`, `INTERNAL_TOKEN` 선택), `tools/list`에 도구 5개만 등록되는 구조(등록 목록을 한 곳에)
- [x] **2. 공통 봉투·오류 정규화** (FR-MCP-007, IF-INT-MCP-001): 성공 `{ok:true, collected_at, data, truncated?}`, 실패 `{ok:false, reason: NO_PERMISSION|NOT_FOUND|ZABBIX_ERROR, collected_at}`. Zabbix 예외·타임아웃을 잡아 `ZABBIX_ERROR`, 권한 오류 → `NO_PERMISSION`, 스택 트레이스 노출 없음. 목록 100건·이력 500점 자르기. **테스트: 150건 → 100건+`truncated`, 5xx → `ZABBIX_ERROR`**
- [x] **3. STALE 판정 유틸** (FR-MCP-008, SAFE-09): `stale = lastclock < now - max(delay×3, 10분)`. **테스트: delay 30s·11분 전 → stale, 2분 전 → not stale(머지 조건)**
- [x] **4. `zabbix_list_problems`** (FR-MCP-002): `problem.get` + `trigger.get(selectHosts)` 보강. fixture 테스트: host id·name 채워짐
- [x] **5. `zabbix_get_problem`** (FR-MCP-003): `event.get` + `trigger.get(expandExpression, selectItems, selectFunctions)` → `expression`, `items[{itemid, key_}]` 포함. 없는 eventid → `NOT_FOUND`
- [x] **6. `zabbix_get_host`** (FR-MCP-004): `host.get` + `hostinterface.get` + `maintenance.get` → `in_maintenance` 불리언
- [x] **7. `zabbix_list_items`** (FR-MCP-005): `item.get(output=[…])` + `key_search` 필터, 아이템마다 `lastclock, delay, stale`
- [x] **8. `zabbix_get_history`** (FR-MCP-006): `history.get(history=value_type, sortfield=clock)` ≤500점, 24h 초과 범위는 `trend.get`으로 `source:"trend"`. 테스트: 48h 요청 시 trend
- [x] **9. 미등록 보장 테스트** (FR-MCP-009, SAFE-03): `tools/list` 결과에 `*_update_*`·`*_create_*`·planned 7개 없음, 이름 5개가 `contracts/mcp-tools.md`와 일치
- [x] **10. 목 모드 E2E 준비** (FR-MCP-010): `ZABBIX_MOCK=true`에서 5도구가 CPU 데모 장애 시나리오(eventid 1건, 호스트 1대, cpu/mem/disk/net 아이템, 1시간 이력)로 일관된 fixture를 돌려주게 — Agent 테스트가 그대로 쓴다
- [x] **11. 마무리**: 엔진 하드코딩 `rg` 0건(아이템 키는 인자로만), LOG 기록
