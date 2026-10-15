# frontend — React + Vite + TypeScript (nginx :80 → 호스트 8080, 유일한 외부 공개 포트)

주담당: 화면·UI 화면 담당(부 연동·인프라 담당) / 공통 컴포넌트·API 연동·MSW 연동·인프라 담당(부 화면 담당).
먼저 읽을 것: 루트 `CLAUDE.md` → `docs/mvp-checklist.md` "Frontend"·"범위 밖" → `contracts/api.md`·`contracts/incident.schema.json` → `docs/night/PLAN-frontend-api.md`(연동 작업 큐).

## 지금 코드의 상태와 원칙
- `dev`의 화면(PR #4)은 목업 기반이다. **화면 구성은 살리고 데이터 형식만 `contracts/api.md`(기획서 7장)로 바꾼다.** 새 화면·새 기능을 만들지 않는다 (기획서 9-0, 검토의견 4-4).
- 범위 밖 화면(비용 절감 `/cost`, 서버 비교 `/compare`, 현황 홈의 평소 범위·디스크 예측·추이·히트맵·서버 간 묶음, `/plans`·`/reports`·`/alerts`·`/admin`)은 **코드를 건드리지 않는다.** 목 데이터 그대로. 메뉴는 "준비 중" 처리(FR-FE-013).
- 자잘한 UI 수정은 바로 고치지 않고 `docs/ui-backlog.md`에 적는다.

## 역할 ([필수] 화면 5개 + 공통)
| 화면·컴포넌트 | 내용 | 담당 | 근거 |
|---|---|---|---|
| 로그인 | `admin`·`oncall`, `POST /api/auth/login` → JWT는 **`sessionStorage`**(루트 CLAUDE.md 결정, localStorage 금지), 401이면 `/login` | 화면 담당 | FR-FE-001 |
| 공통 레이아웃 | 헤더 "DejaFix · Zabbix AI", 메뉴, 상단 연결 상태(`/api/health`: zabbix·agent·mcp_zabbix·shared_db), Zabbix 끊기면 15초 안에 경고 배너 | 화면 담당 | FR-FE-002 |
| 현황 홈 | KPI 4종 `KpiCard`(값은 `Measured`, `unknown`이면 `UnknownValue`) + 새/오래된 장애 목록(심각도 칩·호스트·시작 시각 KST·분석 상태) → 클릭 시 `/incidents/:id` | 화면 담당 | FR-FE-003·004 |
| 장애 상세 `/incidents/:id` | 리포트(요약·영향 범위·원인 TOP3 확신도 **문자 3단계**·확인할 수 없음 목록·사람이 확인할 것·`kind=fallback`이면 "LLM 미연결/실패 — 규칙 기반 최소 리포트" 라벨·분석 상태 배지) + **`EvidenceTrace`**(근거 ID 클릭 → tool·args·called_at·duration_ms·result_summary·data_clock) + **계획 미리보기**(단계별 티어 배지 A 초록 "조회 · 안전" / B 주황 "변경 · 승인 필요(미구현)" / C 빨강 "금지 · 사람이 판단", command_preview·precheck·rollback·risk, 상단 `ReadOnlyNotice`, **실행 버튼·토글 없음**) + **메일 발송 기록**(수신자·sent/failed/skipped·시도·시각). 다시 분석·메일 재발송·검토 버튼은 **렌더하지 않는다** | 화면 담당(상세) · 연동·인프라 담당(EvidenceTrace) | FR-FE-006·007·008·009 |
| AI 어시스턴트 패널 | `POST /api/chat`을 **`fetch` + ReadableStream**으로 읽어 SSE 파싱(`EventSource` 금지 — GET만 되고 `Authorization` 헤더 불가). `token` 순차 표시, `meta`→`final`만 와도 정상, `final.unknowns`·`evidence_ids` 표시, `error` 처리, 장애 상세에서 열면 `context.incident_id` 첨부. 응답이 JSON이면 같은 레이아웃으로 한 번에 표시(탈출 규칙 1) | 연동·인프라 담당 | FR-FE-011·014 |
| `UnknownValue` | `Measured.unknown=true` 또는 `value=null` → "확인할 수 없음 · 사유 · 수집 시각 hh:mm". 0·빈칸·NaN 금지. KPI 확인 불가 호스트는 별도 카운트 | 연동·인프라 담당 | FR-FE-010, SAFE-10 |
| 폴링·API 클라이언트 | react-query `refetchInterval: 15000`(현황 홈·장애 상세·연결 상태), `fetch('/api/…')` + `Authorization: Bearer`, 봉투 해제, `error.code` 처리. WebSocket 없음 | 연동·인프라 담당 | FR-FE-012 |
| MSW | 필수 8개(#1·3·4·5·6·10·11·18) 핸들러 + 채팅 스트림 목, 개발 모드에서만. 목 데이터에 `unknown:true`·fallback 리포트·A/B/C 단계·`failed` 메일 포함 | 연동·인프라 담당 | FR-FE-015 |
| nginx·Dockerfile | 정적 서빙, `/api/*` → `backend:8000` 프록시(SSE 버퍼링 끔), **SPA fallback `try_files $uri /index.html`**(메일 링크 직접 진입 404 방지). 개발은 Vite 5173 `/api` → `localhost:8000` 프록시, 절대 주소 환경 변수 금지 | 연동·인프라 담당 | FR-FE-016, IF-INT-FE-001·002 |

## 하지 않는 것 (기획서 3-2, SAFE-04·10·11·13)
- 키·토큰을 브라우저 저장소(localStorage 포함)나 번들에 두기. 브라우저에는 JWT만(`sessionStorage`)
- Zabbix·Agent 직접 호출 — 모든 요청은 `/api`
- 라벨이 "실행"·"Run"·"Execute"인 button·a·input 요소. 실행 토글·승인 워크플로
- `null`을 0·빈칸·NaN으로 그리기, 확신도 퍼센트·점수 표시
- 분석 문장·원인·티어를 화면에서 계산하거나 바꾸기(표시만, NFR-MAINT-010)
- 엔진 하드코딩: 동작 ID·아이템 키·동작 제목 문자열을 `src/`에 직접 쓰지 않는다(티어 배지 3색과 공통 문구는 허용)
- [선택] 선구현: 별도 장애 목록 화면(필터), 호스트 화면·차트, 리포트 목록·인쇄, 알림 화면, 다시 분석·메일 재발송·검토 버튼, 대화 목록, LLM 사용량. 필수 완료 후 1순위는 티어 판정 근거 표시(FR-FE-028)

## 의존 계약
- `contracts/api.md`(엔드포인트·봉투·`Measured`·`analysis.status`), `contracts/incident.schema.json`(Incident 타입), `contracts/agent-api.md`(SSE 이벤트 `meta/tool_call/tool_result/token/final/error`, 계획 단계 필드 `seq, action_id, title, target, command_preview, tier, rationale, precheck, expected_effect, risk, rollback, evidence_ids`)
- 계약과 다른 점이 보이면 코드로 우회하지 말고 LOG·PR 본문에 "계약 변경 제안"

## 실행
- Node 22 LTS(`.nvmrc` 22, `engines.node >=22 <23`), **npm만**(`npm ci`, `package-lock.json` 커밋)
- 개발: `cd frontend && npm ci && npm run dev` → `http://localhost:5173` (백엔드 없으면 MSW로 전 필수 화면 렌더)
- 빌드: `npm run build` → `dist/` (nginx 이미지에 복사)
- 라이브러리 범위: react-router-dom, @tanstack/react-query, echarts/echarts-for-react, msw, eslint, prettier. xyflow·xterm 설치 금지(충돌 #6)

## 테스트 (PR 머지 조건)
- `npm run lint` · `npx tsc --noEmit` · `npm run build` 전부 통과
- 수동 점검표: DOM에 "실행/Run/Execute" 요소 없음(FR-FE-008) / localStorage에 토큰 없음, 번들에 `sk-`·토큰 문자열 없음(SAFE-13) / 네트워크 탭 폴링 15±2초, `/api/chat` 요청에 `Authorization` 헤더(FR-FE-011·012) / 주소창 `/incidents/1` 직접 입력 → 404 아님(FR-FE-016)
- vitest 컴포넌트 테스트는 [선택]

## 데모 기준
주입 후 15초 안에 현황 홈 목록 맨 위에 새 장애, 상세에서 리포트(fallback 라벨 포함 가능)·근거 패널·A/B/C 배지 계획·메일 기록이 보이고, 어시스턴트에 "이 서버 백업 작업이 원인인가?"를 물으면 "확인할 수 없음 · NOT_COLLECTED"가 나온다(시나리오 D-MAIN·D-UNKNOWN).
