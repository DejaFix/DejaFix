# DejaFix 전체 작업 순서 (요구사항정의서 v1.3 기준)

- 작성일: 2026-10-15 · 작성: DB·메일 담당 · 상태: **초안 (팀장 확인 전)**
- 기준: `DejaFix_요구사항정의서_v1.3.md`(이하 SRS)의 FR·NFR·IF·DR 전 항목. 일정 틀·역할은 `DejaFix_기획서_최종_v1.3.md` 9장·10장, 바뀐 이유는 `DejaFix_기획서_SRS_검토의견.md`.
- 목적: 6명이 **같은 순서표**를 보고 일하게 하고, 이 표를 그대로 노션 작업 현황표의 행으로 옮긴다(8장).
- 원칙
  1. 요구사항 ID 하나는 반드시 어떤 작업(T-번호) 하나에 들어간다. 필수 ID는 전수 대조했다(7-1).
  2. 작업 순서는 **의존 관계**가 정한다. 날짜는 그 위에 얹은 배치일 뿐이다.
  3. 등급은 SRS 그대로. **[필수]가 끝나기 전에 [선택]에 손대지 않는다**(CON-016). [이후]는 순서만 정하고 날짜는 `(TODO: 추후결정)`.
  4. 미결 항목은 `(TODO: 추후결정)`. 기한이 지나도 자동 확정하지 않는다(AS-T07).
  5. 완료 판정은 SRS 수용 기준(G/W/T)이다. 이 문서는 어느 수용 기준을 보라고만 가리킨다.

---

## 1. 작업 단위와 웨이브

### 1-1. 작업(T) 정의

작업 하나 = 한 사람이 한 PR(또는 한 번의 수동 작업)으로 끝낼 수 있는 크기. 크기 표기: **S** 1시간 안 · **M** 반나절 안 · **L** 반나절 넘음(야간 루프에 넘기거나 둘이 나눔).

### 1-2. 웨이브 (의존 순서)

| 웨이브 | 이름 | 들어가는 조건 | 끝나는 조건 |
|---|---|---|---|
| **W0** | 기반 — 저장소·계약·환경·팩 | 없음 | contracts 5종 dev 머지, 노션 문서 2개, 팩 초안, Zabbix 웹·에이전트 보임 |
| **W1** | 목(mock) 기반 병렬 구현 | W0의 계약이 있으면 시작(머지 전엔 기획서 5~7장을 임시 계약으로) | 각 파트가 자기 [필수]를 `ZABBIX_MOCK`·`LLM_FAKE`·MSW로 통과 |
| **W2** | 실연동 전환 | 읽기 전용 토큰·포워딩·데모 트리거 | `ZABBIX_MOCK=false`로 수집→분석(fallback)→화면 |
| **W3** | 엔드투엔드 관통·안정화 | W2 | 주입→화면에 리포트+계획, 안전 테스트 8종 존재, compose 빌드 |
| **W4** | 데모 준비·실행 | W3 | 3분 이내 2회 연속, main 태그·골든 백업, 데모 |
| **W5** | [선택] | W4 종료 + 팀장 승인 | 우선순위 순으로 가능한 만큼 |
| **W6** | [이후] L1 | 데모 피드백 반영 | AWS MCP·일일 수집·웹훅 |
| **W7** | [이후] L2 | W6 | JIRA·RAG·조치 결과 보고서 |
| **W8** | [이후] L3 | W7 | 안전 심사 레이어·평가 하네스·Agent MCP 공개 |
| **W9** | [이후] L4·조건부 | W8 | GPU·제조 팩, 전사 업무 확장(조건부) |

### 1-3. 크리티컬 패스

```
W0  T03 자빅스 API 목록 ─┐
    T54 읽기 전용 토큰 ───┼─► W2  T62 Backend 실연동 ─┐
    T55 포워딩·주소 ─────┘      T63 Scheduler 실폴링 ─┼─► W3 T68 E2E 관통 ─► W4 T75 리허설 2회 ─► T79 데모
W0  T08 packs/it 초안 ──► W1  T51 fallback 리포트·계획 ─┘
W1  T41 MCP 5도구 ──────► W1  T47 고정 수집 세트 ──► W2 T65 Agent 실연결 ─┘
```

**LLM 공급자가 보류**(AS-T02)이므로 데모 기본 경로는 fallback이다. 따라서 크리티컬 패스는 "LLM 호출"이 아니라 **팩 → fallback 리포트·계획 → 티어 강제 → 화면**이다. LLM 호출(T48)·출력 검증(T49)은 공급자가 확정될 때 켜지는 경로라 한 단계 뒤에 둔다.

---

## 2. 작업 목록

열: ID · 작업 · 포함 요구사항 · 주담당(부) · 선행 · 크기 · 산출물 · 완료 판정(SRS 수용 기준 위치).

### W0. 기반 (저장소·계약·환경·팩)

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T01 | 저장소·하네스 정렬 — 루트 `CLAUDE.md`(13-7 ①~⑩), `.env.example` 한 블록, `.claude/settings.json` allow/deny, `.gitattributes`, `.gitignore`, 보완 폴더(`scheduler/ libs/zabbix_ro/ mcp-aws/ docs/night·handoff·demo/`), dev·main 보호 규칙, 기본 브랜치 dev | FR-INF-007, NFR-MAINT-005·008, NFR-SEC-001·006, NFR-SAFE-013, NFR-PORT-003, CON-017 | 연동·인프라 담당(Backend 담당) | — | M | dev에 머지된 설정 파일 | `git ls-files`에 `.env`·`*.db` 없음, `.env.example`에 3-4 전 키, settings deny 확인 |
| T02 | 루트 `pyproject.toml` uv workspace(backend·agent·mcp-zabbix·scheduler·libs/zabbix_ro), 각 멤버 `pyproject.toml`·`.python-version`, `uv.lock` 커밋, 프론트 `.nvmrc`·`engines` | NFR-PORT-001·004·005 | 연동·인프라 담당(Backend 담당) | T01 | M | 2대 이상 PC에서 `clone → uv sync → npm ci` 성공 | NFR-PORT-001 |
| T03 | 자빅스 API 목록(노션) — 수집 항목 CPU/MEM/DISK/Network, 사용할 `*.get` 메서드, 실제 아이템 키 후보 | FR-INF-014(②) | 팀장(Zabbix·MCP 담당) | — | S | 노션 문서 1 | FR-INF-014 T |
| T04 | 프론트 API 요청서(노션) — [필수] 화면 5개별 필요 API·요청·응답 예시 | FR-INF-014(①) | 화면 담당(연동·인프라 담당) | — | M | 노션 문서 1 | FR-INF-014 T |
| T05 | `contracts/api.md` + `contracts/incident.schema.json` v0 — 필수 8개(#1·3·4·5·6·10·11·18) 상세, 나머지 planned, 공통 봉투·`Measured`·오류 코드·`analysis.status` 6값, 채팅 `fetch` 스트림 명시 | FR-INF-008(일부), FR-DATA-006, DR-018, IF-INT-BE-001·002·003·004·005·007·008·011, FR-BE-013(형식), NFR-MAINT-001(계약 우선·2인 승인) | Backend 담당(연동·인프라 담당) | T04 | M | 2파일 dev 머지(2인 승인) | FR-INF-008 T, 요청서 대응표 PR 본문 |
| T06 | `contracts/db-schema.sql` v0 — 필수 11 테이블, 전부 `IF NOT EXISTS`, CHECK(`mode='preview'`, 티어, 상태값), 인덱스, SQLite 2회 연속 실행 확인 | FR-INF-008(일부), FR-DATA-005, DR-001·002·003·004·005·006·007·008·009·010·011·012·014·016·017·019, NFR-MAINT-009 | DB·메일 담당(Backend 담당) | — | M | 1파일 dev 머지 | FR-DATA-005 T, DR-016 |
| T07 | `contracts/agent-api.md` v0 — `/healthz`·`/v1/chat` SSE 이벤트, 리포트·계획 JSON Schema, `unknown_reason` 변환표 | FR-INF-008(일부), IF-INT-AG-001·002, IF-INT-MCP-001(변환표) | DB·메일 담당(팀장) | — | M | 1파일 dev 머지 | IF-INT-AG-002 |
| T08 | `contracts/mcp-tools.md` v0 — 도구 12개(필수 5 상세, 7 planned), 공통 봉투 | FR-INF-008(일부), IF-INT-MCP-001·002·003·004·005·006, FR-MCP-009(문서 부분) | Zabbix·MCP 담당(DB·메일 담당) | T03 | M | 1파일 dev 머지 | FR-MCP-001 T |
| T09 | `packs/it/` 초안 — `metrics.yaml`(cpu·mem·disk·net 별칭), `actions.yaml`(동작·티어·requires·command_preview·precheck·rollback·`fallback_plans`·`default_tier: C`), `prompts/`(분석·계획·채팅) | DR-021, NFR-EXT-002(값 `DOMAIN_PACK=it`), FR-ZBX-007(초안) | 팀장(DB·메일 담당) | — | M | `packs/it/` 3종 | YAML 파싱 통과, `fallback_plans` 동작 ID가 `actions`에 존재, B 동작에 precheck·rollback |
| T10 | Zabbix 서버 VM — 웹 로그인, 버전·설치 방식 기록, `apiinfo.version` 캡처 | FR-ZBX-001, CON-014 | Zabbix·MCP 담당(팀장) | — | S | `docs/zabbix/`, `infra/zabbix/README.md` | FR-ZBX-001 T |
| T11 | Windows agent 2 설치·호스트 등록·지표 수집 확인 | FR-ZBX-002 | 팀장(Zabbix·MCP 담당) | T10 | M | Zabbix 웹 최근 데이터 | FR-ZBX-002 T |
| T12 | 야간 가동 설정(전원 각자 PC) — 절전 해제·Windows Update 일시 중지·`.wslconfig`·VM 헤드리스 자동 시작 | NFR-AVAIL-008·009, NFR-PORT-007 | 전원(총괄 팀장) | — | S | 11-1 체크 | NFR-AVAIL-008 |
| T13 | 야간 루프 지시문·큐 양식 — `docs/night/PROMPT.md`, `PLAN-<파트>.md` 6개, `LOG-<파트>.md` | CON-015 | 연동·인프라 담당(화면 담당) | T01 | S | `docs/night/` | 9-3 템플릿과 일치 |

### W1. 목 기반 병렬 구현

**Frontend** (화면 화면 담당 / 연동·공통 연동·인프라 담당). 기존 `dev` 프론트(PR #4)는 화면 구성을 살리고 **데이터 형식만 `contracts/api.md`로 바꾼다.** 범위 밖 화면(비용·서버 비교·관리자 등)은 "준비 중"으로 두고 손대지 않는다.

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T14 | MSW 핸들러 8개 + 채팅 스트림 목 | FR-FE-015 | 연동·인프라 담당(화면 담당) | T05 | M | `frontend/src/mocks/` | FR-FE-015 T |
| T15 | API 클라이언트·react-query 훅·15초 폴링·`Authorization` 헤더 | FR-FE-012, NFR-PERF-005(폴링) | 연동·인프라 담당(화면 담당) | T05 | M | `lib/api.ts` 교체 | FR-FE-012 T |
| T16 | 로그인 화면·토큰 보관(결정된 위치, localStorage 금지) | FR-FE-001, NFR-SEC-005 | 화면 담당(연동·인프라 담당) | T05 | S | `pages/Login.tsx` | FR-FE-001 T |
| T17 | 공통 레이아웃·헤더·연결 상태 배너(`/api/health`) | FR-FE-002, NFR-AVAIL-004(화면), NFR-OBS-002(화면) | 화면 담당(연동·인프라 담당) | T05 | M | `components/Layout.tsx` | FR-FE-002 T |
| T18 | 현황 홈 — KPI 4종(`Measured`) + 장애 목록 | FR-FE-003·004 | 화면 담당(연동·인프라 담당) | T15 | M | `pages/Dashboard.tsx` | FR-FE-003·004 T |
| T19 | `UnknownValue` 컴포넌트와 전 화면 적용 | FR-FE-010, NFR-SAFE-010 | 연동·인프라 담당(화면 담당) | T05 | S | `components/UnknownValue.tsx` | FR-FE-010 T |
| T20 | 장애 상세 — 리포트 영역(요약·영향·원인 TOP3·확인할 수 없음·fallback 라벨·분석 상태 배지, 선택 버튼 미렌더) | FR-FE-006, NFR-SAFE-011(표시) | 화면 담당(연동·인프라 담당) | T15 | M | `pages/IncidentDetail.tsx` | FR-FE-006 T |
| T21 | `EvidenceTrace` 근거 패널 | FR-FE-007, NFR-SAFE-012(화면), NFR-OBS-001(화면) | 연동·인프라 담당(화면 담당) | T20 | M | `components/EvidenceTrace.tsx` | FR-FE-007 T |
| T22 | 변경 계획 미리보기·티어 배지·`ReadOnlyNotice`(실행 요소 0) | FR-FE-008, NFR-SAFE-004(화면) | 화면 담당(연동·인프라 담당) | T20 | M | 계획 영역 | FR-FE-008 T(DOM 검색) |
| T23 | 장애 상세 메일 발송 기록 | FR-FE-009 | 화면 담당(연동·인프라 담당) | T20 | S | 상세 하단 | FR-FE-009 T |
| T24 | AI 어시스턴트 패널 — `fetch`+ReadableStream 수신, 이벤트 표시, `incident_id` 첨부, 비스트리밍 대체 표시 | FR-FE-011·014 | 연동·인프라 담당(화면 담당) | T15 | L | `components/AssistantPanel.tsx` | FR-FE-011·014 T |
| T25 | "준비 중" 메뉴 정리, 범위 밖 화면 격리 | FR-FE-013 | 화면 담당(연동·인프라 담당) | T17 | S | 메뉴 | FR-FE-013 T |
| T26 | nginx(정적·`/api` 프록시·SSE 버퍼링 해제·SPA fallback)·frontend Dockerfile·Vite 프록시 | FR-FE-016, IF-INT-FE-001·002 | 연동·인프라 담당(화면 담당) | — | M | `frontend/nginx.conf`, `Dockerfile` | FR-FE-016 T |

**Backend** (Backend 담당 / 부 연동·인프라 담당)

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T27 | FastAPI 골격·`/healthz`·공통 응답·오류·페이지네이션 | FR-BE-013, FR-INF-002(backend) | Backend 담당(연동·인프라 담당) | T05 | M | `backend/` 골격 | FR-BE-013 T |
| T28 | `backend.db` 생성·PRAGMA·`shared.db` 읽기 전용 ATTACH(부재 시 `waiting`) | FR-BE-014, IF-INT-DB-001, FR-DATA-004(backend), DR-019, NFR-AVAIL-002(backend) | Backend 담당(DB·메일 담당) | T06 | M | DB 모듈 + 쓰기 거부 테스트 | FR-BE-014 테스트 |
| T29 | 로그인·`me`·역할 기반 접근 제어·시드 계정 2개 | FR-BE-001·002·003, NFR-SEC-004, DR-011 | Backend 담당(연동·인프라 담당) | T28 | M | `/api/auth/*` | FR-BE-001·002·003 T |
| T30 | `libs/zabbix_ro` — 허용 목록 강제·Bearer 토큰·fixture 모드 | FR-LIB-001·002·003, NFR-SAFE-002, FR-BE-015·016, IF-EXT-001 | Backend 담당(Zabbix·MCP 담당) | T02 | M | `libs/zabbix_ro/` + SAFE-02 테스트 | FR-LIB-001 테스트 |
| T31 | 종합 헬스 `GET /api/health`(zabbix·agent·mcp·shared_db·scheduler_last_ok) | FR-BE-004, NFR-OBS-002·004(API) | Backend 담당(연동·인프라 담당) | T28·T30 | S | #4 | FR-BE-004 T |
| T32 | 대시보드 요약 #5 + 실시간 문제 #6 | FR-BE-005·006, IF-INT-BE-004·005 | Backend 담당(연동·인프라 담당) | T30 | M | #5·#6 | FR-BE-005·006 T |
| T33 | 장애 목록 #10 + 장애 상세 #11(리포트·근거·계획·메일 기록 4묶음, `execute` 없음) + Incident 스키마 검증 | FR-BE-008·009, FR-DATA-006, IF-INT-BE-007·008 | Backend 담당(연동·인프라 담당) | T28 | L | #10·#11 | FR-BE-008·009 T |
| T34 | 채팅 중계 #18 — Agent `/v1/chat` SSE 그대로 중계, 비스트리밍 모드 | FR-BE-012, IF-INT-BE-011 | Backend 담당(연동·인프라 담당) | T27 | M | #18 | FR-BE-012 T |

**Scheduler · DB · 메일** (DB·메일 담당 / 부 Backend 담당)

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T35 | 공유 스키마 멱등 적용 모듈(Agent·Scheduler 공용)·PRAGMA·기동 순서 테스트 | FR-DATA-001·002·003, NFR-AVAIL-002(scheduler), NFR-MAINT-009 | DB·메일 담당(Backend 담당) | T06 | M | `libs` 또는 각 서비스 `db.py` | FR-DATA-003 T |
| T36 | Scheduler 폴링 → `incidents` INSERT·해결 처리·호스트 보강 | FR-SCH-001·002·003, NFR-PERF-002, DR-003 | DB·메일 담당(Backend 담당) | T35 | M | `scheduler/` | FR-SCH-001·002·003 T |
| T37 | Scheduler 실패 재시도·`scheduler_jobs.poll_problems`·목 모드 테스트 | FR-SCH-004·005·009, NFR-OBS-004(기록) | DB·메일 담당(Backend 담당) | T36 | M | pytest | FR-SCH-004 T |
| T38 | 메일 워커 — 30초 주기·console 공급자·`dedup_key`·3회 재시도·`mail_logs` 기록 | FR-MAIL-001·003·004·007, NFR-SAFE-016, NFR-AVAIL-005, NFR-OBS-005, NFR-PERF-004, DR-012 | DB·메일 담당(Backend 담당) | T28 | L | `backend/mail/` | FR-MAIL-003 테스트, FR-MAIL-004 T |
| T39 | 메일 수신자(`MAIL_RECIPIENTS`)·제목·본문 7항목·링크 | FR-MAIL-002·005, NFR-MAINT-010(메일은 저장값만 옮김) | DB·메일 담당(Backend 담당) | T38 | S | 템플릿 1개 | FR-MAIL-005 T |
| T40 | Agent 기술 검토 인계 메모 `docs/handoff/<MMDD>-agent.md` + 30분 페어 | (10-3 인수인계) | DB·메일 담당 → 팀장 | — | S | 인계 메모 | 10-3 ①~⑦ |
| T41 | `backup-db.ps1`·복원 절차 | FR-INF-006, NFR-AVAIL-006, DR-020 | DB·메일 담당(연동·인프라 담당) | T35 | S | `infra/scripts/backup-db.ps1` | FR-INF-006 T |

**Zabbix MCP** (Zabbix·MCP 담당 / 부 DB·메일 담당)

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T42 | MCP 서버 골격(streamable HTTP `:8200/mcp`)·`/healthz`·공통 봉투 | FR-MCP-001, FR-INF-002(mcp), IF-INT-MCP-001 | Zabbix·MCP 담당(DB·메일 담당) | T08·T30 | M | `mcp-zabbix/` | FR-MCP-001 T |
| T43 | 필수 5도구(fixture로 동작) | FR-MCP-002·003·004·005·006·010 | Zabbix·MCP 담당(DB·메일 담당) | T42 | L | 도구 5개 + fixture | FR-MCP-002~006 T |
| T44 | 정규화·크기 제한·오류 봉투·오래된 값 판정 | FR-MCP-007·008, NFR-SAFE-009, NFR-PERF-007 | Zabbix·MCP 담당(DB·메일 담당) | T43 | M | pytest | FR-MCP-007·008 테스트 |
| T45 | 쓰기·planned 도구 미등록 보장(`tools/list` 검사 테스트) | FR-MCP-009, NFR-SAFE-003(MCP) | Zabbix·MCP 담당(DB·메일 담당) | T42 | S | pytest | FR-MCP-009 T |

**AI Agent** (팀장 / 부 DB·메일 담당). 사람 셋이 나눈다 — 골격·워커 팀장, 규칙 계열(검증·티어·fallback) DB·메일 담당, MCP 접점 Zabbix·MCP 담당. 폴더 주담당은 팀장이며 PR 승인은 팀장이 한다.

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T46 | Agent 골격·`/healthz`·**도메인 팩 로더**(`DOMAIN_PACK`, 팩 없으면 기동 실패)·엔진 하드코딩 금지 검사 명령 | FR-AG-025, NFR-EXT-001·002, IF-INT-AG-001, FR-INF-002(agent) | 팀장(DB·메일 담당) | T09 | M | `agent/` 골격, `rg` 검사 | FR-AG-025 테스트 |
| T47 | MCP 클라이언트·도구 목록 검사(12개 명시 집합)·위반 시 기동 거부 | FR-AG-010, NFR-SAFE-003(agent), NFR-SAFE-005 | Zabbix·MCP 담당(팀장) | T42·T46 | M | pytest | FR-AG-010 테스트 |
| T48 | 분석 워커(10초)·상태 머신·`agent_runs` 기록·호출자 기록·run 상한 | FR-AG-001·002·014, NFR-SAFE-018(필수 부분), NFR-PERF-008, DR-004 | 팀장(DB·메일 담당) | T46·T35 | L | 워커 | FR-AG-001·002 T |
| T49 | 고정 수집 세트 4도구 순서 호출·`tool_calls` 저장(32KB) | FR-AG-003, NFR-SAFE-012, NFR-OBS-001, DR-005 | Zabbix·MCP 담당(팀장) | T47·T48 | M | COLLECTING 단계 | FR-AG-003 T |
| T50 | 계획 티어 강제(PLANNING, 코드만)·B 롤백 필수·강등 사유·계획 실패 처리 | FR-AG-006·008, NFR-SAFE-006·007, DR-007·008 | DB·메일 담당(팀장) | T46 | M | pytest 3종 | FR-AG-006 테스트 |
| T51 | **fallback 리포트 + fallback 계획**(키 빈 값 경로, `net` 등 목록 없는 유형은 A만) | FR-AG-007·023, NFR-AVAIL-003, NFR-PERF-003(fallback 전환), DR-006 | DB·메일 담당(팀장) | T49·T50 | M | fallback 경로 | FR-AG-007·023 T |
| T52 | OpenAI 호환 LLM 클라이언트·공급자 교체·**가짜 LLM 모드**·1회 호출(허용 동작 ID 목록 프롬프트, `max_tokens` 2000, 45초) | FR-AG-004·012·013, IF-EXT-002, NFR-MAINT-006, NFR-SEC-007(키 한도는 공급자 확정 시) | 팀장(DB·메일 담당) | T46 | L | LLM 모듈 | FR-AG-004·013 T |
| T53 | 출력 검증(VALIDATING) — 스키마·근거 ID 실존·null+사유·TOP3 자름·확신도 3단계 | FR-AG-005, NFR-SAFE-008·011 | DB·메일 담당(팀장) | T52 | M | pytest 4종 | FR-AG-005 테스트 |
| T54 | 채팅 `/v1/chat` SSE·대화 저장·장애 맥락 첨부·LLM 없을 때 규칙 기반 답변(NOT_COLLECTED) | FR-AG-009·011, IF-INT-AG-002, DR-009·010 | 팀장(Backend 담당) | T48 | L | 채팅 경로 | FR-AG-009·011 T |
| T55 | 안전 회귀 세트 — SAFE-06·07 테스트를 `safety_regression` 마커로 묶고 "잘못 통과 x/N, 과잉 차단 y/M" 출력 | NFR-EVAL-001, NFR-MAINT-003(묶음) | DB·메일 담당(팀장) | T50 | S | `pytest -m safety_regression` | NFR-EVAL-001 |

**Zabbix 환경 · 스크립트 · 인프라**

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T56 | 읽기 전용 계정·그룹·API 토큰 발급, `host.update` 권한 오류 캡처, 토큰 DM 3곳 | FR-ZBX-004, NFR-SAFE-001(필수 부분) | Zabbix·MCP 담당(팀장) | T10 | M | `docs/zabbix/` 캡처 | FR-ZBX-004 T |
| T57 | 접속 주소(포워딩 8081·10051 또는 브리지)·방화벽·아침 점검 절차 | FR-ZBX-006, NFR-SEC-002(VM 호스트) | Zabbix·MCP 담당(팀장) | T10 | M | `ZABBIX_URL` 확정값(.env), 점검 절차 | FR-ZBX-006 T |
| T58 | `metrics.yaml` 실제 키 확정(net 인터페이스 이름 포함) | FR-ZBX-007 | 팀장(Zabbix·MCP 담당) | T09·T11 | S | PR | FR-ZBX-007 T |
| T59 | 데모 템플릿 복제(CPU 30초)·데모 트리거 1분 High·호스트 이름 통일 | FR-ZBX-003(CPU), NFR-PERF-006 | 팀장(Zabbix·MCP 담당) | T11 | M | 트리거 1회 발동 | FR-ZBX-003 T |
| T60 | `inject-cpu.ps1`·`cleanup.ps1`(G12 안전 규칙), 데모 PC 1회 시험 | FR-INF-003·005 | Zabbix·MCP 담당(팀장) | — | M | `infra/scripts/` | FR-INF-003·005 T |
| T61 | Dockerfile 4개(Python, 루트 빌드 컨텍스트, `packs/` 포함)·`docker-compose.yml`(5서비스, 8080만 공개, named volume, restart) | FR-INF-001, NFR-SAFE-014(포트), NFR-SEC-002, NFR-AVAIL-001, NFR-PORT-002, NFR-OBS-003 | 연동·인프라 담당(Backend 담당) | T02·T26 | L | `infra/docker-compose.yml` | FR-INF-001 T |
| T62 | 로컬 프로세스 실행 절차(탈출 규칙 3)·`README.md` 실행 방법·폴더 `CLAUDE.md` 실행·테스트 명령 | FR-INF-009, NFR-PORT-005, NFR-MAINT-005(명령) | 연동·인프라 담당(각 주담당) | T02 | S | README | FR-INF-009 T |

### W2. 실연동 전환

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T63 | Backend 실연동 — `ZABBIX_MOCK=false`에서 #5·#6 실데이터, Zabbix 차단 시 `ZABBIX_UNAVAILABLE` | FR-BE-005·006(실), NFR-AVAIL-004(API) | Backend 담당(연동·인프라 담당) | T30·T32·T56·T57 | S | — | B3 DoD ① |
| T64 | Scheduler 실폴링 — 주입 → `incidents` 행, 60초 이내 | FR-SCH-001(실), NFR-PERF-002 | DB·메일 담당(Backend 담당) | T36·T56·T59 | S | — | B3 DoD ② |
| T65 | MCP 5도구 실호출 테스트 | FR-MCP-002~006(실) | Zabbix·MCP 담당(DB·메일 담당) | T43·T56 | S | 테스트 기록 | B3 DoD ③ |
| T66 | Agent ↔ 실 MCP ↔ 실 `incidents` — `LLM_FAKE=true` 1건 + 키 빈 값 fallback 1건 저장 | FR-AG-007·013·023(실), NFR-AVAIL-003 | 팀장(DB·메일 담당) | T48·T49·T51·T65 | M | `analysis_reports`·`change_plans` 행 | B3 DoD ④ |
| T67 | Frontend 실 Backend 전환(MSW 끔)·`UnknownValue`·15초 폴링 확인 | FR-FE-003·004·006·012(실) | 연동·인프라 담당(화면 담당) | T18~T24·T33 | M | — | FR-FE-004 T |
| T68 | 메일 워커 ↔ 상세 #11 메일 기록 연동(console) | FR-MAIL-001·007(실), FR-FE-009(실) | DB·메일 담당(Backend 담당) | T38·T33 | S | — | FR-MAIL-007 T |

### W3. 엔드투엔드 관통·안정화

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T69 | **E2E 관통 1회** — 주입 → 화면에 리포트(fallback 또는 LLM)+계획(티어 배지), 소요 시간 기록 | NFR-PERF-001(예비), NFR-OBS-008 | 팀장(전원) | T63~T68 | M | `docs/demo/` 측정 1행 | B4 마감선 |
| T70 | 필수 안전 테스트 8종 존재 점검(SAFE-02·03·06·07·08·09·dedup·ATTACH) + 린트 통과 | NFR-MAINT-002·003 | 각 파트(점검 연동·인프라 담당) | W1 | S | 체크표 | NFR-MAINT-003 |
| T71 | 버그 수정(야간 루프 2, 새 기능 금지) | — | 각 파트 | T69 | M | `night/*` PR | LOG 기록 |
| T72 | compose 빌드·통합 기동(데모 호스트 PC), 컨테이너 재시작 확인 | FR-INF-001(기동), NFR-AVAIL-001 | 연동·인프라 담당(Backend 담당) | T61 | M | `docker compose ps` 5 Up | FR-INF-001 T |
| T73 | 답변 기준 일원화 코드 리뷰(backend·frontend·scheduler에 LLM 호출·티어 계산 없음), 명명 규칙·단일 작성자·계약 우선·시각 UTC/KST 리뷰 | NFR-MAINT-010·004·001, FR-DATA-002, NFR-PORT-006, DR-017 | DB·메일 담당(Backend 담당) | W1 | S | PR 리뷰 체크 | NFR-MAINT-010 |
| T74 | 데모 시나리오 대본 초안(D-MAIN·D-UNKNOWN, 제안 장면은 채택 TODO)·발표 문구 검수 | (11-5) | 화면 담당(팀장) | T69 | M | `docs/demo/script.md` | 11-5 체크리스트 |

### W4. 데모 준비·실행

| ID | 작업 | 포함 요구사항 | 담당 | 선행 | 크기 | 산출물 | 완료 판정 |
|---|---|---|---|---|---|---|---|
| T75 | Gmail SMTP 실발송(587 막히면 SendGrid 즉시 전환), 테스트 메일 1통 | FR-MAIL-006, IF-EXT-003, NFR-MAINT-007(smtp) | DB·메일 담당(Backend 담당) | T39, 발신 계정 결정 | M | 수신 메일 | FR-MAIL-006 T |
| T76 | 리허설 1·2 — 3분 이내 2회 연속, 감지 여부·리포트 종류 기록 | NFR-PERF-001·002·003·004·005·006, NFR-OBS-008 | 팀장(전원) | T72·T75 | M | `docs/demo/` 기록표 | NFR-PERF-001 |
| T77 | dev → main 머지·main 동결·태그 `release/demo-1016`·골든 백업 | NFR-MAINT-008, NFR-AVAIL-006, DR-020 | 연동·인프라 담당 + DB·메일 담당 | T76(1회차) | S | 태그·`backups/` | NFR-AVAIL-006 |
| T78 | 데모 체크리스트 D-1·T-60·T-10, 녹화 백업 영상, 실패 대체 경로 확인(`ZABBIX_MOCK` 재기동 1분, 로컬 실행) | NFR-AVAIL-007 | 팀장(화면 담당) | T76 | S | 체크 완료 | NFR-AVAIL-007 |
| T79 | 발표 자료 — 기획 요약·차별점 3축·L1~L4 확장 로드맵(멘토 "추가 확장" 논의용) | (9-2 B7) | DB·메일 담당(화면 담당) | — | M | 슬라이드 | 11-5 발표 문구 검수 |
| T80 | 데모 실행·멘토 피드백 노션 기록·`cleanup.ps1` | — | 팀장(전원) | T76~T79 | S | 노션 기록 | — |

### W5. [선택] — 필수 완료 후, 아래 순서대로

| 순서 | ID | 작업 | 포함 요구사항 | 담당(현재 주담당 기준) | 비고 |
|---|---|---|---|---|---|
| 1 | T81 | 티어 판정 근거 표시(`rationale`) + fallback 계획에 `reboot_host`(C) 시연 단계 | FR-FE-028, FR-AG-026 | 화면 담당 / 팀장 | SRS가 "가장 먼저 착수할 선택 항목"으로 지정. FR-AG-026 채택은 `(TODO: 추후결정)` |
| 2 | T82 | 팩 스키마 검증·`packs/README.md` 엔진↔팩 계약 | NFR-EXT-003·005 | 팀장 / DB·메일 담당 | 두 번째 팩(이후)의 전제 |
| 3 | T83 | 원인 TOP3 적중 기록 양식 | NFR-EVAL-002 | 팀장 | 리허설 기록표에 열 추가 |
| 4 | T84 | API #7·#14·#15(호스트 목록·리포트·계획 조회) | FR-BE-007·010·011, IF-INT-BE-006·009·010 (선택 API 묶음 IF-INT-BE-012는 T85~T93에서 해당 API마다) | Backend 담당 | 소비 화면이 생길 때 |
| 5 | T85 | 다시 분석 — Agent API·런 상태·Backend 중계·화면 버튼 | FR-AG-016·017, FR-BE-020·021, FR-FE-020, IF-INT-AG-003·004 | 팀장 / Backend 담당 / 연동·인프라 담당 | |
| 6 | T86 | 계획 검토 기록 — 테이블·API·버튼 | DR-013(`plan_reviews`), FR-DATA-007, FR-BE-022, FR-FE-022 | DB·메일 담당 / Backend 담당 / 화면 담당 | |
| 7 | T87 | 메일 보강 — SendGrid 스위치·수동 발송·발송 기록 조회·테스트 메일·수신자 테이블·시간당 20통 | FR-MAIL-008·009·010·011·012, IF-EXT-004, NFR-SEC-008, FR-FE-019·021 | DB·메일 담당 / 연동·인프라 담당 | |
| 8 | T88 | MCP 선택 도구 3종 + 7일 재발 횟수 수집 | FR-MCP-011·012·013, IF-INT-MCP-007, FR-AG-020 | Zabbix·MCP 담당 / 팀장 | |
| 9 | T89 | 호스트 화면·차트·호스트 API | FR-FE-017, FR-BE-018·019 | 화면 담당 / Backend 담당 | |
| 10 | T90 | 리포트 목록·인쇄, 장애 목록 화면(필터), 대화 목록 | FR-FE-018·005·023, FR-BE-023 | 화면 담당 / 연동·인프라 담당 / Backend 담당 | FR-BE-023 접근 범위 `(TODO: 추후결정)` |
| 11 | T91 | 비용·토큰 기록과 표시, 일일 예산 판정 | FR-AG-019, FR-FE-024, NFR-OBS-007, NFR-SEC-007(세부) | 팀장 / 화면 담당 | LLM 공급자 확정 뒤 |
| 12 | T92 | LLM 고급 — 폴백 모델 재시도, 분석 추가 도구 호출, 채팅 도구 호출 루프, 프롬프트 주입 방어 | FR-AG-012(선택부), FR-AG-015·018·024, NFR-SAFE-015 | 팀장 | 실 LLM 전제 |
| 13 | T93 | 감사 로그(로그아웃·행동 기록)·내부 토큰 | FR-BE-017·024, NFR-OBS-006, NFR-SEC-003, NFR-SAFE-014(토큰) | Backend 담당 | |
| 14 | T94 | 운영 보강 — 디스크 주입·디스크 데모 트리거, Zabbix 역할 허용 목록, 로컬 대체 Zabbix, `check-env.ps1`, 다른 PC 접속, `mcp-aws/` 자리 | FR-INF-004·010·011·012, FR-ZBX-003(디스크), FR-ZBX-005·008, NFR-SAFE-001(역할) | Zabbix·MCP 담당 / 연동·인프라 담당 | |
| 15 | T95 | 개발 품질 — vitest, GitHub Actions 1개, pre-commit | (13-5 선택) | 연동·인프라 담당 | |

### W6~W9. [이후] — 순서만 확정, 날짜는 `(TODO: 추후결정)`

| 웨이브 | ID | 묶음 | 포함 요구사항 | 비고 |
|---|---|---|---|---|
| W6 L1 | T96 | Scheduler 일일 수집·사양 스냅샷·보관 정리 + 이후 테이블 2개 | FR-SCH-006·007·008·009(이후 부분), FR-DATA-008, DR-014(이후 부분)·015 | 구조도 "하루 한 번 수집" |
| W6 L1 | T97 | AWS MCP·비용 절감·서버 비교 화면·비용 API | FR-FE-027, FR-BE-027, (mcp-aws) | AWS 계정 `(TODO: 추후결정)`, 없으면 정적 가격표 목 |
| W6 L1 | T98 | Zabbix 웹훅 수신, 재발 장애 묶기, 디스크 고갈 예측·14일 추이, MCP 이후 도구 4종 | FR-ZBX-009, FR-MCP-014·015·016·017, IF-INT-MCP-008 | G3 권한 확인 포함 |
| W6 L1 | T99 | 관리자·수신자 CRUD·사용자 목록·계획 단독 생성 중계·헬스체크 고도화·HTML 메일 | FR-FE-025, FR-BE-025·026·028, FR-AG-021, IF-INT-AG-005, IF-INT-BE-013, FR-INF-013, FR-MAIL-013 | |
| W7 L2 | T100 | 통합 기획서 7단계 완성 — JIRA 티켓, RAG 트러블슈팅 가이드, 조치 결과 보고서·사후 분석 | FR-LT-013·014·015 | DB 재검토(PostgreSQL+pgvector는 이때, CON-001) |
| W8 L3 | T101 | 실행 전 안전 레이어 원안 — 영향 시뮬레이션·사전 점검·롤백 생성·심사 6종·반대 심문·규칙 엔진 4단계·자율성 L0~L3·조치 실행(테스트 클러스터)·검증 에이전트·사후 검증·drain 2인 승인 검토·모르면 멈춤·기반 붕괴 이관·에이전트 8종 분리 | FR-LT-001·002·003·004·005·006·007·008·009·010·011·012·020·021·022·024, FR-FE-026 | **실행 여부는 정책 코드가 결정, LLM은 결정하지 않음**(통합 기획서 결정 사항) |
| W8 L3 | T102 | 평가 하네스 30~50 시나리오·고급 지표·벤치마크·회귀 평가·목표 지표 확정 | NFR-EVAL-003·004·005·006·007 | "잘못 통과율 0%"를 숫자로 |
| W8 L3 | T103 | Agent 자체 MCP 서버 공개, 두 번째 팩 "YAML만 추가" 실증, 폐쇄망 모드·LLM 사내 호스팅·마스킹 | FR-AG-022, NFR-EXT-004, FR-LT-018·023, NFR-SAFE-017 | 장기 고객 `(TODO: 추후결정)` |
| W9 L4 | T104 | GPU·제조 도메인 팩과 데이터 소스 MCP, 장애 기억·보조 기능·이상 탐지 | NFR-EXT-006, FR-LT-016·017·019 | |
| W9 조건부 | T105 | 전사 업무 확장(게임·CS·마케팅·인프라) — 비IT 팩 1종으로 같은 Agent E2E | NFR-EXT-007 | **조건부 확장 후보**: 필수 완료 후 진행 속도 보고 멘토와 착수 시점 결정. 순서 고정 없음 |

---

## 3. 6명 레인 배치 (필수 W0~W4)

슬롯: **S1** 10/15 오전(09~13) · **S2** 10/15 오후(13~18) · **N1** 10/15 야간 루프(18~08:30) · **S3** 10/16 오전(09~12) · **S4** 10/16 오후(13~데모). 각 칸은 위에서부터 순서. 사람 슬롯은 M 2개 또는 L 1개 + S 1~2개까지만 넣고, 나머지는 N1(야간 루프: 테스트·골격·빌드 같은 기계적 작업)에 넘긴다.

| 사람 | S1 (10/15 오전) | S2 (10/15 오후) | N1 (야간 루프) | S3 (10/16 오전) | S4 (10/16 오후) |
|---|---|---|---|---|---|
| **연동·인프라 담당** | T01 잔여 확인·T02 uv workspace·T13 루프 양식·T04 요청서(부) | T14 MSW 8개·T15 API 클라이언트·T19 UnknownValue | T24 어시스턴트 패널·T26 nginx·T61 compose 빌드 | T21 EvidenceTrace·T67 실 Backend 전환·T72 compose 통합 기동·T62 README | T77 main 머지·태그 / 리허설 지원 |
| **화면 담당** | T04 요청서·T16 로그인·T17 레이아웃·T25 준비 중 메뉴 | T18 현황 홈·T20 장애 상세 리포트 | T22 계획 미리보기·T23 메일 기록 | T67 실데이터 검증(연동·인프라 담당과)·T74 데모 대본 | T78 체크리스트 보조·T79 발표 자료(DB·메일 담당과)·T80 |
| **Backend 담당** | T05 contracts api·schema·T27 골격·T28 DB ATTACH | T29 로그인·RBAC·T30 zabbix_ro → T63 실연동(토큰 오면) | T31 health·T32 #5·#6·T33 #10·#11·T34 #18 | T33·T34 검증·T68 메일 기록 연동·버그 | 리허설 지원 |
| **DB·메일 담당** | T06 db-schema·T07 agent-api·T35 멱등 모듈 | T40 Agent 인계(13:00)·T36 폴링·T37 재시도·T64 실폴링 | T38 메일 워커·T39 본문·T41 백업 스크립트 | T50 티어 강제·T51 fallback 리포트·계획·T55 회귀 세트·T75 SMTP 실발송 | T73 일원화 리뷰·T79 발표 자료·T77 골든 백업 |
| **Zabbix·MCP 담당** | T03 API 목록(부)·T10 VM 기록·T56 토큰(11:00)·T57 포워딩 | T08 mcp-tools.md·T42 MCP 골격·T60 주입 스크립트 | T43 5도구 fixture·T44 정규화·T45 미등록 검사 | T65 실호출·T47 MCP 클라이언트·T49 고정 수집 세트 | 아침 점검·리허설 Zabbix 담당 |
| **팀장** | 09:00 스탠드업(결정 3건)·T03 API 목록·T09 packs/it·T11 agent 설치·T58 키 확정 | T59 데모 트리거·T46 Agent 골격·팩 로더·T48 워커·상태 머신(DB·메일 담당 인계 후 페어) | T52 LLM 클라이언트·가짜 LLM·T54 채팅 | T66 Agent 실연결·T69 **E2E 관통**·T53 검증(DB·메일 담당과) | T76 리허설 1·2·T78 체크리스트·T80 데모 |

**배치 결과로 드러난 것** (7장 검토에서 다시 다룸)
- 기획서 9-2의 "10/15 17:00 E2E 시도 / 18:00 마감선"은 Agent 필수(T46~T54)가 S2 하나에 들어가지 않아 **이 배치로는 S3(10/16 오전)에야 관통된다.** 그래서 Agent를 셋으로 나눴고(T46·T48 팀장, T50·T51·T53·T55 DB·메일 담당, T47·T49 Zabbix·MCP 담당), S2 끝에는 "수집 → fallback 리포트만"이라도 화면에 띄우는 것을 1차 목표로 둔다. 마감선 자체를 옮길지는 팀장 판단.
- Zabbix·MCP 담당 S1이 5개로 가장 빡빡하다. T10은 10/14에 이미 끝났으면 지우고, T57 포워딩이 안 되면 브리지 IP로 넘어가 시간을 끊는다(11:00).
- 화면 담당 S1~S2는 상대적으로 여유 있어 데모 대본·발표(T74·T79)를 받는다.

---

## 4. 선택·이후 배치 (주 단위, 후보)

프로젝트 기간은 기획서 13-4 기준 **7주 규모**로 가정한다. 주차 날짜는 후보이며 멘토·팀 확인 `(TODO: 추후결정)`. 로테이션 2회차(데모 직후, 10-2)가 적용되면 담당은 그때 재배정한다.

| 주 | 기간(후보) | 웨이브 | 내용 |
|---|---|---|---|
| 1주 | 10/13~10/17 | W0~W4 | 필수 전부, 10/16 데모 |
| 2주 | 10/20~10/24 | W5 1~8 → W6 시작 | 선택 상위 8개(T81~T88), 로테이션 2회차 인수인계, 데모 피드백 반영 |
| 3주 | 10/27~10/31 | W5 9~15, W6 L1 | 선택 나머지, L1(T96~T99) |
| 4주 | 11/3~11/7 | W7 L2 | JIRA·RAG·조치 결과 보고서(T100), DB 재검토 |
| 5~6주 | 11/10~11/21 | W8 L3 | 안전 레이어 원안(T101)·평가 하네스(T102)·Agent MCP 공개·두 번째 팩(T103) |
| 7주 | 11/24~11/28 | W9 | GPU·제조 팩(T104), 전사 업무 확장은 조건부(T105) — 멘토와 착수 시점 결정 |

---

## 5. 결정 기한 (TODO)

| 기한 | 항목 | 결정자 | 상태 / 후보 | 막히는 작업 → 미정일 때 |
|---|---|---|---|---|
| 10/14 21:00(경과) | `contracts/` v0 승인 (AS-B02) | 계약 소유자+소비자 | `(TODO: 추후결정 — 후보: 기획서 5~7장 + 노션 문서 2개)` | T05~T08 → 임시 계약으로 W1 진행 |
| 10/15 09:00 | 역할표·로테이션 (AS-B06) | 팀장+멘토 | `(TODO: 추후결정 — 후보: 10-1·10-2 그대로)` | 전 작업 담당 열 → 후보안대로 진행 |
| 10/15 09:00 | JWT 보관 위치 (AS-M14) | 연동·인프라 담당 | `(TODO: 추후결정 — 후보: sessionStorage, 메모리)` | T16 → localStorage만 금지, 한 모듈에 격리 |
| 10/15 09:00 | 활성 팩 변수 이름 (AS-B12) | 팀장(연동·인프라 담당) | `(TODO: 추후결정 — 후보: DOMAIN_PACK)` | T46 → 읽는 곳 한 군데 |
| 10/15 10:00 | agent 실제 아이템 키 (G2) | 팀장 | 기술 확인 | T58 → 공식 템플릿 키 가정 |
| 10/15 11:00 | Zabbix 버전·주소·토큰·포워딩 (AS-B05, G1·G7) | Zabbix·MCP 담당 | `(TODO: 추후결정 — 후보: 7.0 LTS, 포워딩 8081·10051)` | T56·T57 → `ZABBIX_MOCK=true` |
| 10/15 12:00 | **LLM 공급자·키·모델·예산 (AS-B01)** | 팀(조율 DB·메일 담당) | 보류 `(TODO: 추후결정 — 후보: OpenRouter, 팀원 기존 키 / 일 3달러·전체 15달러)` | T52 실 LLM → fallback 데모 확정, 개발은 `LLM_FAKE` |
| 10/15 12:00 | 데모 트리거·시나리오(G6), 점검 시각(G14), 데모 PC(G17), 호스트 이름(AS-M15), 차별점 장면 채택(AS-B11), 주입 스크립트 안전성(G12) | 팀장(G12 Zabbix·MCP 담당) | `(TODO: 추후결정 — 후보: 15:00 / 호스트 연동·인프라 담당 PC·VM Zabbix·MCP 담당 PC·대상 팀장 PC / LAB-PC-DEMO / 11-5 제안 그대로)` | T59·T60·T74·T78 → 후보로 준비 |
| 10/15 13:00 | 대화 접근 범위 (AS-B10) | Backend 담당 | `(TODO: 추후결정 — 후보: 본인 것만)` | T90 → 본인 것만 |
| 10/15 15:00 | 메일 발신 계정 (AS-B07) | DB·메일 담당 | `(TODO: 추후결정 — 후보: 새 공용 Gmail + 앱 비밀번호, SendGrid 대체)` | T75 → console |
| 10/16 데모 | 장기 타깃 고객(G9), AWS 계정(G8) | 멘토 | `(TODO: 추후결정 — 후보: 금융·공공 / AWS는 L1)` | T97·T103 |
| 데모 후 | 2주차 이후 주차 날짜, 전사 업무 확장 착수 시점 | 멘토+팀 | `(TODO: 추후결정)` | 4장 표 |

---

## 6. 마감선·탈출 규칙 (SRS 1-2 용어 정의·CON-005)

| 시각 | 판정 | 실패 시 |
|---|---|---|
| 10/15 18:00 | E2E 관통 | 탈출 1: [선택] 전부 중단, 채팅 SSE → 비스트리밍(T24·T34의 조건부 경로) |
| 10/16 11:00 | Zabbix 실연동 안정 | 탈출 2: `ZABBIX_MOCK=true` + 녹화 영상 |
| 10/16 11:30 | dev → main 머지·동결·태그·골든 백업(T77) | 이후 데모를 막는 버그만, 팀장 승인 |
| 10/16 13:00 | compose 기동 안정 | 탈출 3: 로컬 프로세스 실행(T62) |
| 리허설 3분 초과 | — | ① 메일 워커 30→15초 ② Agent 워커 10→5초 ③ 트리거 창 1m→30s |

---

## 7. 검토 결과 (작성자 자체 검토)

### 7-1. 요구사항 전수 대조

- SRS 표에서 우선순위 칸이 있는 FR·NFR·IF·DR ID를 전부 뽑아 이 문서 2장의 "포함 요구사항" 열과 스크립트(정규식)로 대조했다. 우선순위 칸에 "필수"가 들어가면 필수(조건부·부분 필수 포함)로 셌다.

| 등급 | SRS ID 수 | 이 문서에 있음 | 누락 |
|---|---|---|---|
| 필수 | 178 | 178 | 0 |
| 선택 | 60 | 60 | 0 |
| 이후 | 56 | 56 | 0 |

- 1차 대조에서 9개(NFR-MAINT-001, NFR-PORT-006, NFR-SAFE-005, FR-AG-015·018·024, FR-ZBX-005·008, IF-INT-BE-012)가 빠져 T05·T47·T73·T84·T92·T94에 넣었다. 2차 대조 누락 0.
- 작업 번호 T01~T105는 빠짐·중복 없음. 표 열 수 불일치 0.
- CON-001~018과 AS-*는 작업이 아니라 리뷰 체크리스트·결정 항목이라 5장과 루트 CLAUDE.md로 넘겼다.

### 7-2. 부하·의존 점검

| 사람 | 필수 작업 수(주담당) | 슬롯당 최대 | 비고 |
|---|---|---|---|
| 연동·인프라 담당 | 14 | S3 4개(S 2·M 2) | T61 compose L은 N1 루프가 빌드 반복 |
| 화면 담당 | 11 | S1 4개(S 3·M 1) | 가장 여유, 데모 대본·발표 흡수 |
| Backend 담당 | 11 | N1 4개 | #10·#11(T33) L은 루프 + S3 검증 |
| DB·메일 담당 | 15 | S3 4개(M 3·S 1) | Agent 규칙 계열 3개를 받아 S3가 무겁다 → T55는 S로 작음, T75는 발신 계정 결정 뒤라 오후로 밀릴 수 있음 |
| Zabbix·MCP 담당 | 12 | S1 5개 | 11:00 토큰이 전부의 앞에 있어 S1 과부하. T10이 끝났으면 제외 |
| 팀장 | 13 + 스탠드업·데모 | S2 4개(M 3·L 1) | 팀장·Agent·에이전트·데모가 겹침. Agent 분담이 전제 |

의존 역전 없음: 모든 작업의 선행이 같은 웨이브 이전 또는 같은 슬롯 이전에 있다. 단, T47·T49(Zabbix·MCP 담당)가 S3에 있어 T66 Agent 실연결(S3)과 같은 슬롯이다 → S3 안에서 **T47·T49 → T66 → T69 순서**를 지켜야 한다.

### 7-3. 기획서 9-2와 다른 점 (팀장 확인 필요)

1. **E2E 관통 시점**: 기획서 10/15 17:00 시도·18:00 마감선 → 이 배치에서는 10/16 오전 관통. S2 끝에는 "수집 → fallback 리포트가 화면에"까지만 목표. 마감선을 그대로 두고 탈출 규칙 1을 실질 발동할지, 마감선을 10/16 10:00로 옮길지 결정 필요.
2. **Agent 3분할**: SRS 담당은 팀장 단독. 이 문서는 DB·메일 담당(검증·티어·fallback·회귀 세트), Zabbix·MCP 담당(MCP 클라이언트·고정 수집)으로 나눴다. 폴더 주담당·PR 승인은 팀장 그대로.
3. **노션 자빅스 API 목록(T03) 주담당**을 Zabbix·MCP 담당 → 팀장으로 바꿨다. Zabbix·MCP 담당 S1 과부하 분산, 팀장이 아이템 키를 직접 확인하기 때문.
4. 야간 루프 1(10/14 밤)은 돌지 않았으므로 그 작업 목록이 S1~S2의 낮 작업이 됐다. 기획서 B1 DoD ①②③⑥은 W0 완료 조건으로 흡수.
5. 이미 끝난 것: T01의 대부분(PR #3, 10/15 09:xx dev 머지 — 루트 CLAUDE.md·`.env.example`·settings·`.gitattributes`·보완 폴더·`docs/mvp-checklist.md`), 프론트 코드 dev 이관(PR #4). T02 uv workspace는 아직 없다. T10도 10/14에 됐을 가능성이 높다.

### 7-4. 남은 위험

- LLM 공급자가 끝까지 보류면 D-MAIN의 원인 TOP3는 "확인할 수 없음"으로 나온다(검토의견 4-2). T52는 S3까지 끝내 두어 키만 넣으면 켜지게 한다.
- 11:00까지 토큰이 없으면 W2 전체가 S3로 밀린다. 그 경우 S2는 전원 목 기반으로 W1을 끝내는 데 쓴다.
- 6명 중 3명(팀장·DB·메일 담당·Zabbix·MCP 담당)이 크리티컬 패스에 있다. 이 셋은 S2~S3에 다른 요청을 받지 않는다(기획서 9-1).

---

## 8. 노션 작업 현황표로 옮길 때

- 행 = 2장의 T 한 줄. 열 = `ID` · `웨이브` · `파트` · `작업` · `포함 요구사항` · `주담당` · `부담당` · `선행` · `크기` · `슬롯(배치)` · `상태(대기/진행 중/완료/BLOCKED)` · `산출물 링크(PR·노션)` · `막힌 이유` · `완료 판정(SRS 위치)`.
- 보기: ① 담당자별 보드(상태 열) ② 슬롯·웨이브순 표(스탠드업용) ③ BLOCKED만 ④ 요구사항 ID로 검색.
- 갱신 규칙: 자기 줄의 상태만 바꾼다. PR을 올리면 산출물에 링크, 머지되면 완료. 30분 넘게 막히면 BLOCKED + 이유. Claude Code 세션은 읽기만 한다(여러 세션 동시 쓰기 금지, 기획서 13-7).
- 초기 상태: T01 완료(PR #3), 프론트 이관 완료(PR #4), 나머지 대기.
