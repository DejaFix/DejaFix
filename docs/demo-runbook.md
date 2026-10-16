# 데모 런북 — 리허설·10/16 데모 순서 (DejaFix · Zabbix AI)

> 기준: dev `5d1cbf4`(10/15 밤). 시나리오 원문 `docs/demo/README.md`, 대체 경로 판단 `docs/demo/fallback-paths.md`, 탈출 규칙 `docs/mvp-checklist.md` 5장.
> 이 문서는 **"무엇을 어떤 순서로 치고, 무엇이 보이면 통과인가"** 만 적는다. 결정·담당은 위 문서를 따른다.
> 명령은 전부 **저장소 루트**(PowerShell)에서. `.env`는 사람이 편집한다(Claude Code는 열지 않음).

## 0. 한눈에 보기

| # | 단계 | 명령·행동 | 통과 기준 | 걸리는 시간 |
|---|---|---|---|---|
| 1 | 사전 점검 | 1장 체크리스트 | 전부 ✔ | T-60분 |
| 2 | 서비스 기동 | `scripts\dev-up.ps1`(로컬) 또는 compose | 5개 OK | 1~2분 |
| 3 | 시드·DB 준비 | 3장 (백업 → 시드) | `/api/incidents` 6건 | 10초 |
| 4 | 장애 주입 | 목: 자동 / 실서버: `inject-cpu.ps1 -Minutes 5` | 새 장애가 목록 맨 위 | 목 ≤ 15초 · 실서버 ≤ 3분 |
| 5 | D-MAIN | 장애 상세 → 리포트·근거·계획·메일 | 5장 표 | 1분 30초 |
| 6 | D-UNKNOWN | 어시스턴트에 "이 서버 백업 작업이 원인인가?" | "확인할 수 없음 · NOT_COLLECTED" | 30초 |
| 7 | 정리 | `infra\scripts\cleanup.ps1`, `scripts\dev-down.ps1` | 부하 0개 | 1분 |

---

## 1. 사전 점검 (T-60분)

| 항목 | 확인 방법 | 기대 |
|---|---|---|
| dev 최신 | `git pull origin dev` | 데모 태그 이후면 `main`/`release/demo-1016` |
| 의존성 | `uv sync` · `cd frontend; npm ci` | 오류 없음 |
| `.env` 36행 `APP_BASE_URL` | **값에 공백 없음**(빈 값 또는 `http://<IP>:8080` 형식, #83) | `uv run --env-file .env python -c "print(1)"`에 경고 없음 |
| `.env` DB 경로 | 로컬 실행이면 `SHARED_DB_PATH=data/shared.db`, `BACKEND_DB_PATH=data/backend.db` (compose는 `/data/...`를 compose가 덮어씀) | Windows에서 `/data/...`면 Backend가 "backend.db 폴더가 없습니다"로 기동 실패(#75) |
| `.env` 모드 | 목: `ZABBIX_MOCK=true` / 실서버: `false` + `ZABBIX_URL`·`ZABBIX_API_TOKEN`(#59) | — |
| `.env` 메일 | `MAIL_RECIPIENTS`(비면 발송 안 함), `MAIL_PROVIDER`(데모 PC만 `smtp`) | 테스트 메일 1통 |
| `.env` LLM | 비어 있으면 fallback(정상, 공급자 TODO: 추후결정) | 화면 라벨 "LLM 미연결/실패 — 규칙 기반 최소 리포트" |
| 이전 주입 없음 | `powershell -ExecutionPolicy Bypass -File infra\scripts\cleanup.ps1` | "남은 부하 프로세스 0개" |

## 2. 서비스 기동

### 2-1. 로컬 프로세스 (경로 C, 현재 검증된 방법) — PR #106
```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1            # 목 모드(ZABBIX_MOCK=true 강제)
powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 -Live      # 실서버 모드(.env 값 그대로)
```
- 순서: MCP `:8200` → Agent `:8100` → Scheduler → Backend `:8000` → Frontend `:5173`(`VITE_MSW=off`). 각 `/healthz`를 기다려 표로 보여 준다.
- `.env`는 `scripts/run_with_env.py`가 python-dotenv로 읽는다. **`uv run --env-file`을 쓰지 않는다**(공백 있는 값에서 그 줄 이후를 버림, #83).
- 이미 쓰는 포트는 SKIP(떠 있는 프로세스를 끄지 않음). 종료는 `scripts\dev-down.ps1`(dev-up이 띄운 PID만).

| 서비스 | 통과 표시 |
|---|---|
| mcp-zabbix | `{"ok":true,"zabbix":"mock"}` (실서버면 `"zabbix":"live"` 등) |
| agent | `{"ok":true,"model":null,"mcp":{"zabbix":"ok"}}` — `model: null`은 LLM 미설정(fallback) |
| scheduler | `poll_problems ok seen=… inserted=…` |
| backend | `{"status":"ok"}` |
| frontend | `http://localhost:5173` 200 |

### 2-2. compose (경로 A) — PR #108, **빌드 미검증**
```powershell
docker compose -f infra/docker-compose.yml up -d --build
docker compose -f infra/docker-compose.yml ps            # 5개 Up
```
- 공개 포트는 `8080`(frontend) 하나. 브라우저는 `http://<데모 호스트 PC>:8080`.
- 10/16 13:00까지 `ps`에 Up 아닌 서비스가 있거나 `/api/health`가 재기동 1회로 안 풀리면 **탈출 규칙 3 → 2-1 로컬 프로세스**.

### 2-3. 연결 확인 (공통)
- 화면 상단 칩: `Zabbix 정상 · Agent 정상 · MCP 정상 · DB 정상`. Agent·MCP가 "끊김"이면 2-1 표의 해당 서비스 로그(`data\logs\*.err.log`).

## 3. 시드·DB 준비 (리허설마다 같은 출발점)
```powershell
# 1) 백업 (지우기 전에 반드시) — SQLite 백업 API라 서비스가 켜져 있어도 됨. backups\<시각>\ 에 2파일 + integrity_check (#105)
powershell -ExecutionPolicy Bypass -File infra\scripts\backup-db.ps1
# 2) 서비스를 끈 뒤(scripts\dev-down.ps1) 두 DB를 함께 지우고 다시 시드 — 떠 있으면 파일이 잠겨 지워지지 않음
Remove-Item data\shared.db*, data\backend.db* ; uv run --no-project --python 3.12 python -I scripts\seed_dev.py   # scripts\seed_dev.py 는 PR #106
```
- **`shared.db`만 다시 시드하지 않는다.** 리포트 id가 1부터 다시 매겨져 `backend.db`의 예전 `mail_logs`(같은 `report_id`)가 새 리포트에 붙어 보이고, dedup 키(`auto:<report_id>:<수신자>`) 때문에 새 리포트 메일이 **발송되지 않는다**(10/15 밤 E2E에서 확인 — 08:05 기록이 09:14 리포트에 "발송됨"으로 표시). `backend.db`를 다시 만들면 계정도 `.env` 비밀번호로 새로 생긴다.
- 메일 워커(#86)는 `dedup_key`가 없는 **모든** 리포트에 보낸다. 다시 시드하거나 `MAIL_RECIPIENTS`를 바꾸면 시드 리포트(1·2와 분석된 3)에도 한 통씩 나간다. `MAIL_PROVIDER=smtp`로 데모하면 수신자가 시드 장애 메일도 받는다(10/16 새벽 E2E, #86 코멘트).
- 골든 백업(10/16 11:30): `powershell -ExecutionPolicy Bypass -File infra\scripts\backup-db.ps1 -Label golden` — 라벨 붙은 백업은 자동 정리되지 않는다.
- 시드 결과: 장애 1~6(상태별 예시, `docs/integration.md` 3장). 계정은 `.env`의 `DEMO_ONCALL_PASSWORD`로 처음 만들어질 때만 설정된다 — 비밀번호를 바꿨으면 `backend.db`도 백업 후 다시 시드.
- 확인: `oncall` 로그인 → 현황 홈 목록 6건(3 → 1 → 4 → 5 → 2 → 6).

## 4. 장애 주입

### 4-1. 목 모드 (`ZABBIX_MOCK=true`) — 리허설·탈출 규칙 2
- 주입 명령이 없다. Scheduler가 `scheduler/dejafix_scheduler/fixtures/mock_zabbix.json`의 장애 2건을 첫 주기에 넣는다.
  - **eventid 30001 · demo-host · CPU High** ← 데모에 쓸 장애(MCP fixture와 ID가 같아 수치·근거가 붙음, #81)
  - eventid 90002 · MOCK-PC-02 · 디스크(해결됨) ← MCP fixture에 없어 도구가 `NOT_FOUND` → 수치가 "확인할 수 없음". **데모 화면에서 열지 않는다**(아래 6장 ④)
- 화면 값은 고정 JSON이다. 주입 스크립트로 CPU를 올려도 바뀌지 않으니 "실측"이라는 말을 쓰지 않는다(`fallback-paths.md` 2-3).

### 4-2. 실서버 모드 (`ZABBIX_MOCK=false`) — 경로 A
```powershell
powershell -ExecutionPolicy Bypass -File infra\scripts\inject-cpu.ps1 -Minutes 5    # 데모 PC에서
```
- 1분 평균 CPU 트리거(High, T59) → Zabbix Problem → Scheduler 다음 주기(기본 30초) → `incidents` → Agent 분석(10초 주기).
- 합격선: 주입부터 화면 리포트까지 **3분 이내**(리허설 2회 연속). 측정은 `docs/demo/README.md` 리허설 표.
- 전제: 팀 VM Zabbix 주소·읽기 전용 토큰(#59), 데모 PC 호스트 등록·트리거(T59). **10/15 밤 기준 미확보** → 11:00 점검에서 실패하면 탈출 규칙 2.

## 5. 기대 화면

### D-MAIN — CPU 과부하 (장애 상세 `/incidents/<id>`)
| 화면 위치 | 통과 기준 | 확인 방법(화면이 이상할 때) |
|---|---|---|
| 현황 홈 | 새 장애가 목록 맨 위, 심각도 "높음", 분석 배지 "규칙 기반 리포트"(fallback) 또는 "분석 완료"(LLM) | `GET /api/incidents` 첫 행 |
| 리포트 | fallback 라벨, 수치 cpu·mem·disk·net에 **값과 근거 ID**(목 30001: cpu 96.1% 등) | `GET /api/incidents/<id>` → `report.facts[].evidence_ids` |
| 근거(EvidenceTrace) | 도구 4회(get_problem·get_host·list_items·get_history), 모두 성공·ms 표시 | `evidence[].ok` 전부 true |
| 계획 미리보기 | 상단 "미리보기 전용" 안내, A·B·C 배지, **실행 버튼·토글 없음** | 개발자 도구에서 "실행/Run/Execute" 요소 0개 |
| 메일 발송 기록 | "발송됨 시도 1회"(또는 실패면 "실패 시도 3회 + 사유") | `mail_logs[]` |

- 대사: "승인자는 명령어 한 줄이 아니라 되돌리는 방법까지 같이 봅니다. 그리고 이 화면에는 실행 버튼이 없습니다."
- 시드 장애 1(정상 LLM 리포트 예시)로 B 단계 롤백·C 단계 "금지 · 사람이 판단"을 보여 줄 수 있다(D-BLOCK, 채택은 TODO: 추후결정).

### D-UNKNOWN — "확인할 수 없음"
- 장애 상세 → "AI에게 묻기" 또는 어시스턴트 패널에 **"이 서버 백업 작업이 원인인가?"**
- 통과: 답변에 "확인할 수 없음 · NOT_COLLECTED"(지어내지 않음). Agent가 없으면 "Agent 연결 안 됨"(`AGENT_UNAVAILABLE`) → 2-3 확인.
- 시드 장애 1 상세의 "확인할 수 없음" 목록(백업 작업 여부 · NOT_COLLECTED)으로도 같은 메시지를 보여 줄 수 있다(어시스턴트가 막혔을 때 대체).

## 6. 실패 시 대처

| 증상 | 원인 후보 | 대처 | 목표 시간 |
|---|---|---|---|
| ① Backend가 뜨자마자 종료 | `JWT_SECRET` 없음 / DB 경로가 `/data/...`(Windows) | `data\logs\backend.err.log` → `.env` 수정 후 dev-up 재실행 | 1분 |
| ② Agent `mcp.zabbix` ≠ ok | MCP 미기동 / `INTERNAL_TOKEN` 불일치 | MCP 먼저 확인 → dev-up이 `.env`를 같은 런처로 읽는지(직접 `uv run --env-file` 쓰지 않기) | 1분 |
| ③ 새 장애가 안 보임 | Scheduler 미기동 / 실서버 트리거 미발동 | `data\logs\scheduler.err.log`의 `poll_problems` → 실서버면 Zabbix 웹 Problem 확인 → 안 풀리면 **탈출 규칙 2**(목 모드) | 1분 |
| ④ 수치가 전부 "확인할 수 없음 · TOOL_ERROR/NOT_FOUND" | 목 장애 90002를 열었음 / MCP fixture와 ID 불일치 | 30001 장애로 진행. 그래도면 ②. **지어낸 값이 아니라 정상 동작**이라고 설명 가능 | 즉시 |
| ⑤ 리포트가 60초 넘게 없음 | LLM 지연·실패 | 그대로 진행 — fallback 리포트가 뜬다("LLM 실패에도 흐름 유지", 경로 A) | — |
| ⑥ 메일 기록 없음 | 메일 워커 미연결(#72, PR #86 머지 전) / `MAIL_RECIPIENTS` 빈 값 | 화면의 계획·근거까지만 시연하고 메일은 "보고 단계 출력"으로 설명. 시드 장애 1·2의 sent/failed 기록으로 대체 | 즉시 |
| ⑦ compose 서비스 Up 아님 | 이미지 빌드·환경 | 재기동 1회 → 안 되면 **탈출 규칙 3**: `docker compose down` 후 2-1 로컬 프로세스 | 3분 |
| ⑧ 화면 전체 실패 | — | **경로 D** 녹화 영상 | 즉시 |

### 탈출 규칙 (`docs/mvp-checklist.md` 5장 — 번호 주의)
1. **규칙 1** (10/15 18:00 E2E 미관통): [선택] 전부 중단, 채팅 비스트리밍. → 10/15에 목 모드로 관통해 **미발동(안)**, `docs/decisions/015-e2e-mock-result.md`.
2. **규칙 2** (10/16 11:00 Zabbix 불안정): **목 모드 전환** — `.env` `ZABBIX_MOCK=true`(사람) → 로컬이면 `dev-down` 후 `dev-up`(기본이 목 모드), compose면 `up -d` → `/api/health`의 zabbix ok → 4-1 시나리오. D-MAIN 주입 장면은 녹화 영상으로.
3. **규칙 3** (10/16 13:00 compose 불안정): 2-1 로컬 프로세스로.

## 7. 10/15 E2E에서 실제로 막혔던 것 (해결 상태, 10/15 밤)

| # | 막힌 것 | 증상 | 원인 | 해결 | 상태 |
|---|---|---|---|---|---|
| 1 | `.env` 파싱 | Agent·Scheduler·MCP가 `.env` 값 없이 뜸(`INTERNAL_TOKEN` 불일치) | `uv run --env-file`이 따옴표 없는 값의 공백(`APP_BASE_URL=http://<데모 호스트 PC IP>:8080`)에서 그 줄 이후를 버림. 세 서비스는 `.env`를 직접 안 읽음 | `.env.example` 빈 값으로(PR #89), 기동은 python-dotenv 런처(PR #106) | ⏳ #89·#106 리뷰 중, **로컬 `.env` 36행은 각자 수정** |
| 2 | 에이전트 MCP 미연결 | 도구 호출 전부 0ms 실패, 수치 전부 TOOL_ERROR, 그런데 `/healthz`는 mcp ok | Agent가 항상 `UnavailableToolClient` 사용 | 실 MCP 클라이언트(PR #80) | ✅ #82 닫힘. 장애 30001에서 도구 4건 ok·수치에 근거 확인 |
| 3 | 메일 미연결 | 새 리포트에 메일 기록 없음 | Backend lifespan에 `start_mail_worker` 없음(워커 자체는 정상, `run_once` 수동 sent·dedup 확인) | PR #86 | ⏳ #86 승인됨·머지 대기(#72) |
| 4 | 목 장애 90002 NOT_FOUND | 두 번째 목 장애는 수치가 전부 "확인할 수 없음" | #81이 목의 첫 장애만 MCP fixture(30001)에 맞춤 | 데모는 30001 사용. 90002를 쓰려면 MCP fixture 추가 또는 목에서 제거(to-mcp/to-agent) | ⏳ 판단 필요 |
| 5 | 로컬 DB가 `C:\data`에 생김 | 빈 `backend.db` 생성, 시드가 안 보임 | `.env`의 compose 경로 `/data/...`가 Windows에서 `C:\data`로 풀림 | 상대경로·`.env`를 저장소 루트 기준으로(PR #78), 절대경로 폴더 없으면 기동 실패 | ✅ 머지됨, `.env.example` 주석은 PR #79 |

## 8. 정리 (데모·리허설 후)
```powershell
powershell -ExecutionPolicy Bypass -File infra\scripts\cleanup.ps1     # 부하 0개
powershell -ExecutionPolicy Bypass -File scripts\dev-down.ps1          # 로컬 기동분만 종료
```
- 리허설 측정값은 `docs/demo/rehearsal-log.md`에 누적, 멘토 피드백은 노션.
