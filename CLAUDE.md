# DejaFix

Zabbix 알람이 뜨면 AI가 **조회만으로** 원인 후보·영향 범위를 정리하고, 조치는 **계획(미리보기)으로만** 내며, 모든 수치에 **근거**를 붙여 담당자에게 메일로 보내는 장애 대응 코파일럿. 화면 부제는 "Zabbix AI". 6명이 각자 Claude Code로 개발한다.

## 0. 작업 기준 문서
- **매 작업의 기준은 `docs/mvp-checklist.md`** (금요일 10/16 데모의 [필수]만 뽑은 요약본). 먼저 읽는다.
- 원본 `docs/plan.md`(기획서 v1.3)·`docs/requirements.md`(요구사항정의서 v1.3)는 참고용이고 **동결**이다. 더 늘리지 않는다.
- 코드·문서가 다르면 **`contracts/` > `docs/plan.md` > `docs/requirements.md`** 순으로 따른다.
- 파트별 야간 작업 큐는 `docs/night/PLAN-<파트>.md`, 자잘한 UI 수정사항은 `docs/ui-backlog.md`에 모은다(바로 고치지 않음).

## ① 우선순위 원칙
멘토 지시(노션) > 멘토 구조도 > #세팅 채널 결정 > 통합 기획서·기존 기획서.

## ② 안전 3원칙과 SAFE 규칙 (어기는 코드는 머지 불가)
1. **운영 Zabbix는 `*.get` 조회만**. 쓰기·설정 변경 없음.
2. **변경은 계획(미리보기)까지**. 실행 API·필드·버튼·토글 자체가 없다.
3. **근거 없는 값은 "확인할 수 없음" + 수집 시각**. 지어내지 않는다.

| 규칙 | 요약 | 강제 위치 |
|---|---|---|
| SAFE-02 | `libs/zabbix_ro`는 허용 목록 밖 메서드를 네트워크 요청 **전에** 예외 | Backend·MCP·Scheduler 공통 |
| SAFE-03 | MCP에 쓰기 도구 등록 금지, Agent는 기동 시 도구 목록 검사 후 위반이면 기동 실패 | mcp-zabbix, agent |
| SAFE-04 | `change_plans.mode`는 `'preview'`만, 응답에 `execute`/`run` 필드 없음 | DB·API·화면 |
| SAFE-05 | Agent에 셸·SSH·임의 HTTP 도구 없음. 외부 조회는 MCP로만 | agent |
| SAFE-06·07 | 티어는 `actions.yaml` 매칭으로 **코드가** 지정(LLM 티어 무시, 미등록 → C). B는 precheck·rollback 없으면 C 강등 | agent PLANNING |
| SAFE-08·09 | 모든 수치·사실에 `evidence_ids` 필수, 없거나 오래된 값(`max(주기×3, 10분)`)은 `null`+`unknown_reason` | agent, mcp-zabbix |
| SAFE-10·11 | 화면은 `null`을 0·빈칸으로 그리지 않고 `UnknownValue`로. 확신도는 low/medium/high만(퍼센트 금지) | frontend, 스키마 |
| SAFE-12 | 모든 run·도구 호출은 `agent_runs`·`tool_calls`에 기록, EvidenceTrace로 노출 | agent, frontend |
| SAFE-13·14 | 키는 `.env`만, 프론트 번들에 키 없음. 외부 공개 포트는 8080 하나 | 전 구간, compose |
| SAFE-16 | 메일 수신자는 `.env` `MAIL_RECIPIENTS`만, 리포트당 수신자별 1회(`dedup_key`) | backend |

- 호출 방향은 한 방향: **Frontend → Backend → Agent → MCP → 외부**. 역방향(Agent→Backend, Scheduler→Agent) 금지.
- 운영 Zabbix를 직접 부르는 곳은 Backend·mcp-zabbix·Scheduler 3곳뿐, 모두 `libs/zabbix_ro` 경유. Agent는 Zabbix를 직접 부르지 않는다.

## 스택
| 영역 | 표준 |
|---|---|
| Frontend | React + Vite + TypeScript, Node 22 LTS, **npm**(`npm ci`), react-router-dom, @tanstack/react-query, echarts, msw |
| Backend·Agent·MCP·Scheduler | Python 3.12, FastAPI, **uv** workspace(`uv.lock` 커밋, pip·poetry 금지) |
| DB | **SQLite 2파일**(`/data/shared.db`, `/data/backend.db`), WAL, named volume `dejafix-data`. 별도 DB 컨테이너 없음. **PostgreSQL 사용 안 함** |
| 모니터링 | Zabbix(Ubuntu VM, 우리 compose 밖 외부 서비스) |
| LLM | OpenAI 호환 클라이언트, `LLM_BASE_URL`로 교체. 공급자 (TODO: 추후결정). 미설정이면 fallback 리포트·계획 |
| 메일 | Gmail SMTP(대체 SendGrid), 개발 기본 `MAIL_PROVIDER=console` |

- DB 규칙: 테이블마다 작성자 1개(shared = Agent·Scheduler, backend.db = Backend). Backend는 `ATTACH 'file:/data/shared.db?mode=ro'`로 읽기만. 스키마 원본은 `contracts/db-schema.sql`(전 문장 `IF NOT EXISTS`), MVP 중 `ALTER` 금지.
- 실시간 갱신은 **15초 폴링**, 채팅만 SSE. WebSocket 없음.
- 브라우저 채팅 스트림은 `fetch` + ReadableStream으로 읽는다. `EventSource` 금지(POST·Authorization 헤더 불가).
- **JWT는 `sessionStorage`에 보관**한다. `localStorage` 금지. 키·토큰을 브라우저 저장소에 두지 않는다.

## ③ 폴더 소유권 (기획서 10-1, 후보안 — 승인 (TODO: 추후결정))
**자기 폴더 밖 파일은 수정하지 않는다.** 필요하면 담당자에게 요청하거나 PR 본문·LOG에 "변경 제안"으로 남긴다. 한 세션에서 여러 파트 폴더를 동시에 고치지 않는다.

| 폴더 | 주담당 | 부담당 |
|---|---|---|
| `frontend/` 화면·UI | 배병환 | 장재현 |
| `frontend/` 공통 컴포넌트·API 연동·MSW | 장재현 | 배병환 |
| `backend/` API·인증·메일 워커 | 김준하(메일 노예진) | 장재현 |
| `libs/zabbix_ro/` | 김준하 | 이재헌 |
| `agent/`, `packs/it/actions.yaml`·`prompts/` | 이태윤 | 노예진 |
| `packs/it/metrics.yaml`, `infra/zabbix/` | 이태윤 | 이재헌 |
| `mcp-zabbix/` | 이재헌 | 노예진 |
| `scheduler/` | 노예진 | 김준하 |
| `infra/scripts/` (주입·정리·점검·백업) | 이재헌 | 이태윤 |
| 루트, `.claude/`, compose·Dockerfile, `docs/night/` | 장재현 | 김준하 |
| `docs/demo/` | 이태윤 | 배병환 |
| `docs/` 기획 문서 | 노예진 | 배병환 |
| `mcp-aws/` | [이후] 미배정 | — |

## ④ 계약 변경 절차
- `contracts/`(`api.md`, `agent-api.md`, `mcp-tools.md`, `db-schema.sql`, `incident.schema.json`)가 파트 간 유일한 약속이다.
- 계약 변경은 **계약 PR → 구현 PR** 순서. 계약 PR은 **2인 승인**(계약 소유자 + 소비자 파트 1명).
- 계약을 바꾼 PR에서 `docs/plan.md`의 해당 절도 함께 고친다.
- Claude Code는 `contracts/`를 직접 편집하지 않는다(훅으로 차단). 필요하면 계약 변경 제안을 쓴다.

## ⑤ 명명 규칙
| 대상 | 규칙 | 예 |
|---|---|---|
| 서비스 폴더·compose 서비스 | kebab-case, MCP는 `mcp-<대상>` | `mcp-zabbix`, `scheduler` |
| Python 패키지 | snake_case | `mcp_zabbix`, `dejafix_agent` |
| MCP 도구 | `zabbix_<동사>_<대상>` | `zabbix_list_problems` |
| 환경 변수 | 대문자 + 서비스 접두사 | `ZABBIX_*`, `LLM_*`, `SMTP_*` |
| DB 테이블 | 복수형 snake_case | `analysis_reports` |
| REST 경로 | `/api/<복수 명사>` kebab-case | `/api/mail-logs` |
| 시간 | DB는 UTC ISO8601 문자열, 화면만 KST | `2026-10-16T01:23:45Z` |

## ⑥ 범위 등급 — [필수] 외 기능을 제안·구현하지 않는다
- 등급: **[필수]** 금요일 데모 / **[선택]** 필수 완료 후 / **[이후]** 금요일 이후(L1~). 상세는 `docs/mvp-checklist.md`.
- **[필수]가 전부 끝나기 전에는 [선택]에 손대지 않는다.** 새 기능은 스스로 추가하지 않는다.
- [필수] 요약: Backend API 8개(#1·3·4·5·6·10·11·18), MCP 도구 5개, 테이블 11개, 화면 5개(로그인·레이아웃·현황 홈·장애 상세·AI 어시스턴트 패널), 주입 스크립트 CPU 1종.
- 범위 밖 화면(비용 절감·서버 비교·평소 범위·디스크 예측·히트맵 등)은 **화면만 있고 API는 [이후]**다. 코드를 건드리지 않는다.
- 탈출 규칙: 10/15 18:00 E2E 미관통 → [선택] 전부 중단·채팅 비스트리밍 / 10/16 11:00 Zabbix 불안정 → `ZABBIX_MOCK=true` / 10/16 13:00 compose 불안정 → 로컬 프로세스 데모.

## ⑦ 브랜치·커밋·PR — 간소화 Git Flow
- `main`: 배포·데모 안정본. **직접 push 금지.** dev → main 머지는 데모·배포 시점에만(팀장 승인), 데모 버전은 main 태그(`release/demo-1016`).
- `dev`: 개발 통합 브랜치, GitHub 기본 브랜치. **직접 push 금지.** PR + 승인 1명 이상, squash 머지.
- 작업 브랜치는 dev에서 따서 dev로 PR: `feat/<영역>-<주제>`, `fix/<영역>-<주제>`, `docs/<주제>`, `night/<파트>-<MMDD>`(야간 루프 전용). 영역 = `frontend|backend|agent|mcp|scheduler|libs|infra|contracts|docs`.
- release·hotfix 브랜치는 쓰지 않는다. 10/16 11:30 dev → main 머지 후 main 동결.
- 커밋: Conventional Commits, 한 커밋 한 목적. 예) `feat(agent): 리포트 JSON 스키마 검증 추가`.
- PR: 400줄 이하 권장. 본문 = 무엇 / 왜 / 테스트 방법 / **계약 변경 여부** / **충돌 확인 결과**(노션·`contracts/`·`docs/plan.md` 기준으로 다른 파트와 충돌하는지 1줄).
- Claude가 만든 코드도 사람 리뷰 없이 dev에 들어가지 않는다.

## ⑧ 비밀값
- 토큰·비밀번호·API 키는 **`.env`에만**. `.env` 커밋 금지, 저장소에는 값 없는 `.env.example`만.
- Claude Code는 `.env`를 읽거나 편집하지 않는다(`.claude/settings.json` deny + 훅). 프롬프트·로그·커밋에 키를 붙여넣지 않는다.
- 전달은 Slack 1:1 DM만. 유출 의심 시 즉시 재발급.

## ⑨ 차별점 3축과 코드 규칙
1. **공통 엔진 + 도메인 팩**: 엔진 코드(`agent/ backend/ scheduler/ mcp-zabbix/ libs/ frontend/src/`)에 IT 전용 아이템 키·동작 ID·동작 제목·명령 문구를 하드코딩하지 않는다. `packs/${DOMAIN_PACK}/`(`metrics.yaml`·`actions.yaml`·`prompts/`)에서 로드한다. `packs/it` 문자열도 설정 기본값 1곳에만.
2. **실행 전 안전 레이어**: 티어는 코드·규칙(`actions.yaml`)이 결정하고 **LLM은 결정하지 않는다.** B 단계는 롤백 필수.
3. **멘토 구조도 원칙**: 분석 리포트·변경 계획·채팅 답변 문장은 **AI Agent 한 곳에서만** 만든다. Backend·Frontend·Scheduler는 원인·티어·분석 문장을 생성·변경하지 않는다. 호출자는 `agent_runs.caller`로 구분.

하드코딩 검사(머지 조건, 테스트·fixture·주석 외 0건이어야 함):
```
rg "system\.cpu\.util|vm\.memory\.util|vfs\.fs\.size|check_top_process|check_disk_usage|restart_service|clean_temp_files|reboot_host|delete_recursive" agent backend scheduler mcp-zabbix libs frontend/src
```

## ⑩ 미결 항목은 `(TODO: 추후결정)`
- 팀 결정이 끝나지 않은 값(LLM 공급자·모델·예산, 메일 발신 계정, Zabbix 버전·접속 방식, 데모 호스트 이름 등)은 **Claude가 임의 기본값으로 채우지 않는다.** 환경 변수·yaml·목(mock)으로 비워 두고 `(TODO: 추후결정)`으로 표시한다.

## 린트·테스트 (PR 머지 조건)
| 영역 | 명령 |
|---|---|
| Python | `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` |
| Frontend | `npm run lint`, `npx tsc --noEmit`, `npm run build` |

- 필수 안전 테스트 8종: SAFE-02 쓰기 메서드 거부, SAFE-03 쓰기 도구 감지 시 기동 거부, SAFE-06 미등록 → C, SAFE-07 rollback 누락 → C 강등, SAFE-08 근거 없는 수치 → null, SAFE-09 오래된 값 → unknown, 메일 dedup, Backend ATTACH 쓰기 거부. 빠지면 머지 불가.
- 안전 회귀 세트: `uv run pytest -m safety_regression` → "잘못 통과 0/N".

## 기타
- 경로는 항상 상대경로를 쓴다.
- 편집 후 자동 포맷 훅: `frontend/`는 prettier, Python은 ruff format(`.claude/settings.json`).
- 변경분 검사: `plan-reviewer` 서브에이전트(`.claude/agents/plan-reviewer.md`)가 SAFE 위반·계약 불일치·[이후] 침범·엔진 하드코딩을 보고한다(수정은 하지 않음).
- 노션은 사람이 갱신한다. Claude는 읽기만 한다.

## 폴더
`frontend/ backend/ agent/ scheduler/ mcp-zabbix/ mcp-aws/(README만, L1) libs/zabbix_ro/ packs/it/ contracts/ infra/(scripts/) docs/(night/)`
