# 데모 대체 경로 (NFR-AVAIL-007)

> 담당 팀장 · 부 화면 담당. 근거: `docs/mvp-checklist.md` 5장 탈출 규칙, `docs/work-order.md` 6장 마감선·T62·T78, `docs/demo/README.md` "실패 시".
> 목적: 10/16 데모에서 Zabbix나 compose가 불안정해도 **멈추지 않고 같은 시나리오(D-MAIN·D-UNKNOWN)를 끝까지** 보여 준다.

## 1. 언제 어느 경로로 바꾸나

| 마감선 / 증상 | 판단 기준 | 바꿀 경로 | 결정자 |
|---|---|---|---|
| 10/15 18:00 E2E 미관통 | 주입 → 화면 리포트까지 1회도 못 감 | **탈출 1**: [선택] 전부 중단, 채팅 SSE → 비스트리밍 JSON | 팀장 |
| 10/16 11:00 Zabbix 실연동 불안정 | 아래 2-1 점검 중 하나라도 실패 | **탈출 2 (경로 B)**: `ZABBIX_MOCK=true` + 녹화 영상 | 팀장 + Zabbix·MCP 담당 |
| 10/16 13:00 compose 기동 불안정 | `ps`에 Up 아닌 서비스, 또는 `/api/health` 실패가 재기동 1회로 안 풀림 | **탈출 3 (경로 C)**: 로컬 프로세스 실행 | 팀장 + 연동·인프라 담당 |
| 시연 중 분석이 60초 넘게 안 나옴 | 장애 상세에 리포트 없음 | **경로 A** 그대로 진행: fallback 리포트("LLM 실패에도 흐름 유지") | 발표자 |
| 시연 중 전체 실패 | 화면이 안 뜨거나 1분 안에 복구 불가 | **경로 D**: 녹화 영상 | 발표자 |

- 경로 A가 기본이고 B → C → D 순으로 내려간다. 한 번 내려가면 데모가 끝날 때까지 다시 올리지 않는다.
- 공급자·키 미정(LLM)은 실패가 아니다. 키가 비어 있으면 처음부터 fallback 리포트(`kind='fallback'`, 화면 라벨 "LLM 미연결 — 규칙 기반")로 같은 흐름이 간다.

## 2. 경로별 절차

### 경로 A — 기본 (compose + 실 Zabbix)
`docs/demo/README.md` 체크리스트대로 진행한다.

### 경로 B — Zabbix 대신 고정 데이터 (`ZABBIX_MOCK=true`)
**2-1. 전환 판단 (11:00 점검, 하나라도 실패면 전환)**
1. 데모 PC 에이전트가 팀 서버에서 "사용 가능"인지 (`infra/zabbix/tools/active_check_probe.py` 결과가 `success`)
2. 읽기 전용 토큰으로 `apiinfo.version`·`host.get` 응답 (`infra/zabbix/tools/zabbix_api_probe.py`)
3. 데모 트리거 1회 발동 → `problem.get`에 보임

**2-2. 전환 (목표 1분)**
1. 데모 호스트 PC `.env`에서 `ZABBIX_MOCK=true` (사람이 편집. Claude Code는 `.env`를 열지 않는다)
2. `.env`를 바꾼 뒤에는 `restart`가 아니라 `up -d` (루트 `README.md` "compose 실행")
3. `/api/health`에서 `zabbix`가 `ok`인지 확인 (Backend는 mock일 때 ok로 표시)

**2-3. 달라지는 것 — 발표에서 먼저 말한다**
- 장애·수치는 고정 JSON(fixture)이다. 주입 스크립트로 CPU를 올려도 화면 값은 바뀌지 않는다 → D-MAIN은 **녹화 영상(경로 D)으로 주입 장면만 보여 주고**, 분석·계획·근거·"확인할 수 없음" 장면은 실제 화면으로 한다.
- "실측"이라는 말을 쓰지 않는다(`docs/demo/README.md` 발표 문구 검수와 같은 기준).

### 경로 C — 로컬 프로세스 (compose 없이)
루트 `README.md` "로컬 실행"과 같은 명령. 터미널 5개, 저장소 루트에서:
```powershell
uv sync
uv run --package mcp-zabbix python -m mcp_zabbix                    # :8200/mcp
uv run --package agent uvicorn dejafix_agent.main:app --port 8100
uv run --package backend uvicorn dejafix_backend.main:app --port 8000
uv run --package scheduler python -m scheduler
cd frontend; npm ci; npm run build; npm run preview                  # 빌드본 (탈출 규칙 3)
```
- 로컬에서는 서비스 주소가 컨테이너 이름이 아니라 `localhost`다. `.env`의 `AGENT_URL`·`MCP_ZABBIX_URL`·`SHARED_DB_PATH`·`BACKEND_DB_PATH`를 로컬 값으로 바꾼 별도 `.env`가 필요하다(값은 사람이 준비, 저장소에 올리지 않음).
- 브라우저 주소가 8080이 아니라 `npm run preview`가 알려 주는 주소로 바뀐다. T-10분 탭을 그 주소로 다시 연다.

### 경로 D — 녹화 영상
- D-1(10/15 18:00 이후) E2E가 처음 성공한 회차를 화면 녹화해 둔다(촬영 담당은 `docs/demo/README.md` D-1 항목).
- 영상만으로 진행할 때도 D-UNKNOWN("확인할 수 없음")은 가능하면 실제 화면으로 보여 준다.

## 3. 준비 상태 (2026-10-15 15시, dev `0746f9f` 기준)

| 항목 | 상태 | 경로 영향 |
|---|---|---|
| Agent 로컬 기동 (`packs/it/metrics.yaml` 포함) | `/healthz` 200 확인됨 (PR #41) | C 가능 |
| Backend 로컬 기동, `ZABBIX_MOCK` 설정 | 코드 있음 (`zabbix_mock` 기본 true) | B·C 가능 |
| `mcp-zabbix` 서버·fixture | **골격만** (`mcp_zabbix/__init__.py`) — T42·T43 | B·C 모두 이 산출물이 있어야 함 |
| `scheduler` 실행 모듈 | **골격만** (`scheduler/__init__.py`) — T36 | B·C 모두 필요 |
| `infra/docker-compose.yml` | **없음** — T61·T72 | A의 전제 |
| 주입·정리 스크립트 | **없음** (`infra/scripts/README.md`만) — T60 | A·D(녹화)의 전제 |
| 팀 서버 호스트 등록 | 이 PC는 `host not found` 상태 | A의 전제 → 미해결이면 B |
| 데모 트리거(1분 평균 CPU High) | 미작성 — T59, 팀 서버 관리자 권한 필요 | A의 전제 |

→ 지금 상태로는 **경로 B·C도 MCP 서버와 Scheduler가 있어야** 끝까지 간다. 이 둘이 10/16 오전까지 없으면 남는 대체 경로는 경로 D뿐이다.

## 4. 리허설에서 확인할 것 (T78)
- [ ] 경로 B 전환을 실제로 1회 해 보고 걸린 시간 기록 (목표 1분)
- [ ] 경로 C 다섯 프로세스를 데모 호스트 PC에서 1회 기동, `/api/health` 전부 ok
- [ ] 녹화 영상 파일 위치와 재생 PC 확인
- [ ] 결과를 `docs/demo/rehearsal-log.md` 비고 칸에 "경로 B/C/D 시험" 으로 남김
