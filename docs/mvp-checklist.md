# DejaFix 금요일(10/16) MVP 체크리스트 — [필수]만

- 기준: `docs/plan.md` v1.3 2-4 등급표 + `docs/requirements.md` v1.3의 [필수] 항목. 두 원본은 **동결**(참고용), 작업 기준은 이 파일.
- 충돌 시 `contracts/` > `docs/plan.md` > `docs/requirements.md`.
- **[필수]가 전부 끝나기 전에는 [선택]에 손대지 않는다.** 이 파일에 없는 기능은 만들지 않는다.
- 괄호 안은 근거 ID(기획서 절 / 요구사항 ID). 미결 값은 `(TODO: 추후결정)` — 임의로 채우지 않는다.

## 1. 데모 완료 기준
- [x] 학원 PC에 CPU 부하 주입 → Zabbix Problem → Scheduler 30초 안 수집 → Agent가 MCP로 조회·분석 → 리포트 + 변경 계획(미리보기) → 웹 화면 → 담당자 메일, **주입 후 3분 안, 리허설 2회 연속** (NFR-PERF-001)
- [x] LLM 공급자가 미정이면 `kind='fallback'` 리포트 + fallback 계획("LLM 미연결 — 규칙 기반" 라벨)으로 같은 흐름 → 데모 완료로 인정. 가짜 LLM(`LLM_FAKE=true`)은 데모 금지 (요구사항 2-2)
- 시간 예산(최대): 에이전트 수집 30초 + 트리거 60초 + Scheduler 30초 + Agent 60초 + 메일 40초. 넘으면 메일 워커 15초 → Agent 워커 5초 → 트리거 창 30초 순으로 조정 (4-4)

## 2. 파트별 [필수]

### Zabbix (Zabbix·MCP 담당·팀장)
- [x] VM 서버 웹 로그인, `apiinfo.version` 응답 캡처 `docs/zabbix/` (FR-ZBX-001)
- [x] 학원 PC 1~2대 agent 2, 데모 PC `system.cpu.util` 최신값 2분 이내 (FR-ZBX-002)
- [x] 데모 트리거 `avg(/<데모 호스트>/system.cpu.util,1m)>85` High, CPU 아이템 30초(템플릿 복제본) — 호스트 이름 (TODO: 추후결정) (FR-ZBX-003)
- [x] 읽기 전용 계정·API 토큰, `host.update` 권한 오류 1회 확인 (FR-ZBX-004, SAFE-01 일부)
- [x] 접속 주소·아침 점검 절차 (TODO: 추후결정 — 포트 포워딩 / 브리지 IP) (FR-ZBX-006)
- [x] `packs/it/metrics.yaml` 실제 키: cpu·mem(`vm.memory.util`)·disk·**net**(`net.if.in/out`, 멘토 지시) (FR-ZBX-007)

### Scheduler (DB·메일 담당)
- [x] 30초 `problem.get` → `incidents` INSERT(중복 없음)·resolved, `trigger.get`으로 호스트 보강 (FR-SCH-001~003)
- [x] 실패해도 생존·재시도, `scheduler_jobs.poll_problems` 1행 UPSERT (FR-SCH-004·009), 목 모드 테스트 (FR-SCH-005)

### libs/zabbix_ro (Backend 담당)
- [x] 6-2 허용 목록 밖 메서드는 요청 전 예외, Bearer 토큰, `ZABBIX_MOCK` fixture (FR-LIB-001~003)

### mcp-zabbix (Zabbix·MCP 담당) — 도구 5개만 등록
- [x] streamable HTTP `:8200/mcp`, `zabbix_list_problems`·`zabbix_get_problem`·`zabbix_get_host`·`zabbix_list_items`·`zabbix_get_history` (FR-MCP-001~006)
- [x] 공통 봉투(`collected_at`, 100건·500점 자르기 `truncated`, 오류 `{ok:false, reason}`), STALE 판정 `max(delay×3, 10분)` (FR-MCP-007·008)
- [x] 쓰기·planned 도구 미등록, 목 모드 (FR-MCP-009·010)

### Agent (팀장·DB·메일 담당)
- [x] 분석 워커 10초, severity ≥ `ANALYZE_MIN_SEVERITY`, 장애당 자동 1회, resolved도 분석 (FR-AG-001)
- [x] 상태 머신 + `reported`; LLM 미설정·실패·타임아웃은 **`done`+`error`**(FAILED 아님) (FR-AG-002)
- [x] 고정 수집 세트 4종 → `tool_calls`(`ev_` id, ≤32KB) (FR-AG-003)
- [x] LLM 1회 호출로 리포트+계획, `max_tokens` 2000, 45초, **프롬프트에 팩 허용 동작 ID 목록** (FR-AG-004)
- [x] 검증: 근거 없는 수치 → null+`unknown_reason`, 원인 ≤3, 확신도 3단계 (FR-AG-005)
- [x] PLANNING은 코드만: `actions.yaml` 티어, 미등록 C, B rollback 없으면 C 강등 (FR-AG-006)
- [x] fallback 리포트 + **fallback 계획**(`fallback_plans`, 목록 없는 유형 `net` 등은 A 단계만), 계획 실패 처리 (FR-AG-007·008·023)
- [x] 채팅 `/v1/chat` SSE(meta/final/error 필수), 대화 저장, 장애 맥락 첨부, LLM 없으면 규칙 기반 답변 (FR-AG-009·011)
- [x] 기동 시 MCP 도구 목록 검사(명시 집합) → 위반 시 기동 실패 (FR-AG-010)
- [x] OpenAI 호환 클라이언트(키 없이도 기동), `LLM_FAKE`, `caller` 기록, 도메인 팩 로더(`DOMAIN_PACK`) (FR-AG-012~014·025)

### Backend (Backend 담당·DB·메일 담당) — API 8개만
| # | API | 요구사항 |
|---|---|---|
| 1 | `POST /api/auth/login` (시드 `admin`·`oncall`, bcrypt) | FR-BE-001 |
| 3 | `GET /api/auth/me` | FR-BE-002 |
| 4 | `GET /api/health` (`shared_db:"waiting"` 허용, `scheduler_last_ok`) | FR-BE-004 |
| 5 | `GET /api/dashboard/summary` (KPI 4종 `Measured`) | FR-BE-005 |
| 6 | `GET /api/problems` (`incident_id` 매칭) | FR-BE-006 |
| 10 | `GET /api/incidents` (`analysis.status` 6값, 커서) | FR-BE-008 |
| 11 | `GET /api/incidents/{id}` (리포트·근거·계획·단계·메일 기록, `mode:"preview"`, `execute` 없음) | FR-BE-009 |
| 18 | `POST /api/chat` (Agent SSE 그대로 중계, 막히면 비스트리밍 JSON) | FR-BE-012 |
- [x] 역할 검사, 공통 봉투·오류 코드(`ZABBIX_UNAVAILABLE`)·커서, `shared.db` `mode=ro` ATTACH, `ZABBIX_MOCK`, Zabbix 조회는 `zabbix_ro`만 (FR-BE-003·013~016)
- [x] 메일 워커 30초: `MAIL_RECIPIENTS` 전원, `dedup_key`, 3회 재시도, 제목·본문 7항목·`APP_BASE_URL/incidents/{id}`, smtp·console (FR-MAIL-001~007)

### Frontend (화면 담당·연동·인프라 담당) — 화면 5개 + "준비 중" 메뉴
- [x] 로그인: JWT는 **`sessionStorage`**(localStorage 금지) (FR-FE-001)
- [x] 공통 레이아웃: "DejaFix · Zabbix AI", 연결 상태(`/api/health`), 끊기면 배너 (FR-FE-002)
- [x] 현황 홈: KPI 4종(`UnknownValue`), 새/오래된 장애 목록 → 상세 이동 (FR-FE-003·004)
- [x] 장애 상세 `/incidents/:id`: 리포트(요약·영향·원인 TOP3·확인할 수 없음·fallback 라벨), **EvidenceTrace**(tool_calls), 계획 미리보기(A/B/C 배지·precheck·rollback, **실행 버튼 없음**, ReadOnlyNotice), 메일 발송 기록. 다시 분석·메일 재발송·검토 버튼은 **렌더하지 않음** (FR-FE-006~009)
- [x] `UnknownValue`: "확인할 수 없음 · 사유 · 수집 시각" (FR-FE-010)
- [x] AI 어시스턴트 패널: `POST /api/chat`을 **`fetch` + ReadableStream**으로 수신(`EventSource` 금지), unknowns·근거 표시, 장애 맥락 첨부 (FR-FE-011)
- [x] 15초 폴링(react-query), MSW 필수 8개 + SSE 목, Vite `/api` → `localhost:8000` 프록시 (FR-FE-012·015, IF-INT-FE-002)
- [ ] 비용 절감·서버 비교 메뉴는 "준비 중", API 호출 없음 (FR-FE-013)
- [x] nginx: `/api` 프록시(SSE 버퍼링 끔) + SPA fallback `try_files $uri /index.html` (FR-FE-016)
- 조건부: 탈출 규칙 1 발동 시 채팅 비스트리밍 JSON 표시 (FR-FE-014)

### 데이터 (DB·메일 담당) — 테이블 11개
- [x] shared 9: `incidents, scheduler_jobs, agent_runs, tool_calls, analysis_reports, change_plans, plan_steps, conversations, messages` / backend 2: `users, mail_logs` (FR-DATA-005)
- [x] `contracts/db-schema.sql` 전 문장 `IF NOT EXISTS`, Agent·Scheduler 둘 다 기동 시 적용, `ALTER` 금지, WAL·`busy_timeout=5000`·`foreign_keys=ON` (FR-DATA-003·004)
- [x] 테이블별 단일 작성자, `change_plans.mode` CHECK `'preview'` (FR-DATA-002·005)

### 인프라·운영 (연동·인프라 담당·Zabbix·MCP 담당·DB·메일 담당)
- [x] `infra/docker-compose.yml` 5개 서비스, 공개 포트 8080만, Python 서비스는 루트 빌드 컨텍스트, named volume, `restart: unless-stopped` (FR-INF-001)
- [x] backend·agent·mcp-zabbix `/healthz` (FR-INF-002)
- [x] `infra/scripts/inject-cpu.ps1`·`cleanup.ps1`·`backup-db.ps1`(골든 백업 10/16 11:30) (FR-INF-003·005·006)
- [x] `.env.example` 한 블록(3-4), `.gitignore`(.env·*.db·backups/), `contracts/` 5종 dev 머지 (FR-INF-007·008)
- [x] 노션: 프론트 API 요청서(화면 담당·연동·인프라 담당) + 자빅스 API 목록(Zabbix·MCP 담당·팀장) → `contracts/` 확정 (FR-INF-014, 멘토 순서)
- 조건부: compose 불안정 시 로컬 프로세스 데모 (FR-INF-009)

## 3. 안전 규칙 [필수]
- SAFE-02·03·04·05·06·07·08·09·10·11·12·13·14(포트)·16(수신자 고정). SAFE-01은 읽기 전용 그룹까지만, SAFE-15·내부 토큰은 [선택].
- **필수 테스트 8종(빠지면 머지 불가)**: SAFE-02 쓰기 메서드 거부 / SAFE-03 쓰기 도구 감지 시 기동 거부 / SAFE-06 미등록 → C / SAFE-07 rollback 누락 → C 강등 / SAFE-08 근거 없는 수치 → null / SAFE-09 오래된 값 → unknown / 메일 dedup / Backend ATTACH 쓰기 거부 (NFR-MAINT-003)
- 안전 회귀 세트 `uv run pytest -m safety_regression` → "잘못 통과 0/N, 과잉 차단 y/M" (NFR-EVAL-001)
- 엔진 하드코딩 `rg` 검사 0건 (NFR-EXT-001·002, 루트 CLAUDE.md ⑨), 분석 문장은 Agent 한 곳에서만 (NFR-MAINT-010)

## 4. 범위 밖 — 손대지 않음
### 기존 프론트 화면 (화면만 있음, API는 이후)
| 화면 / 위젯 | 경로 | 상태 |
|---|---|---|
| 비용 절감 | `/cost` (`pages/Cost.tsx`) | **화면만 있음, API는 이후** (L1, AWS MCP). 코드 수정 안 함 |
| 서버 비교 | `/compare` (`pages/ServerCompare.tsx`) | **화면만 있음, API는 이후** (L1, AWS MCP). 코드 수정 안 함 |
| 평소 범위·디스크 예측·추이·히트맵·서버 간 묶음 | 현황 홈(`pages/Dashboard.tsx`) 위젯 | 화면만 있음, API는 이후. 코드 수정 안 함 |
| 변경 계획 목록·상세, 리포트, 알림, 관리자 | `/plans`, `/reports`, `/alerts`, `/admin` | [선택]/[이후] API(#14·#15·#21·#24 등). 필수 완료 전 손대지 않음 |
- "화면만 있음" 화면은 목(mock) 데이터를 그대로 두고, 실 API 연동·데이터 형식 전환 대상에서 뺀다. 메뉴 "준비 중" 처리 방식은 FR-FE-013 기준으로 화면 담당이 결정.

### 기능 ([선택]·[이후])
- [선택]: API #2·7·8·9·12·13·14·15·17·19~22, MCP 도구 3개(`event_history`·`list_triggers`·`api_version`), 다시 분석·런 상태, 채팅 LLM 도구 루프·폴백 모델, 토큰·비용 기록, 계획 검토, 수신자 테이블·SendGrid, 디스크 주입, 별도 장애 목록 화면, 호스트 화면·차트, 티어 판정 근거 표시(FR-FE-028, 필수 후 1순위)
- [이후]: AWS MCP·비용 절감·서버 비교 API, 웹훅, 일일 수집·retention, 관리자·수신자 CRUD API, Agent 자체 MCP 서버, 조치 실행·승인, JIRA·RAG, 영향 범위 그래프, FR-LT 전체
- 자잘한 UI 수정은 `docs/ui-backlog.md`에 모으고 [필수] 완료 후 한 번에 개선.

## 5. 탈출 규칙 (일정이 밀리면 순서대로)
1. 10/15 18:00 E2E 미관통 → [선택] 전부 중단, 채팅 비스트리밍
2. 10/16 11:00 Zabbix 실연동 불안정 → `ZABBIX_MOCK=true` + 녹화 영상
3. 10/16 13:00 compose 불안정 → `uv run`·`npm run preview` 로컬 프로세스 데모

## 6. 미결 (TODO: 추후결정) — 값을 임의로 채우지 않음
LLM 공급자·키·모델·예산 / 메일 발신 계정 / Zabbix 버전·설치 방식·접속 방식 / 데모 호스트 이름·데모 PC·멘토 점검 시각 / 역할표·로테이션 승인 / 대화 접근 범위 / `contracts/` v0 승인 / 데모 차별점 장면 채택. (JWT 보관 위치는 `sessionStorage`로 결정 — 루트 CLAUDE.md)
