# backend

FastAPI BFF (:8000, 내부 전용). 로그인(JWT)·화면용 API 8개·채팅 SSE 중계·메일 워커. `backend.db`에 쓰고 `shared.db`는 읽기 전용 ATTACH로만 읽는다. 화면 표시용 Zabbix 조회는 `libs/zabbix_ro`로 직접 하되 AI 판단용 조회는 하지 않는다. 분석 문장·원인·티어를 만들거나 바꾸지 않는다.

규칙·실행·테스트는 `CLAUDE.md`. 계약은 `contracts/api.md`·`contracts/incident.schema.json`(제공).

## 실행 (저장소 루트, PowerShell)

```powershell
uv sync
uv run --package backend uvicorn dejafix_backend.main:app --port 8000
```

처음 실행에는 `.env`(루트, 사람이 만든 것)에 `JWT_SECRET`과 `DEMO_*_PASSWORD`가 있어야 합니다. `JWT_SECRET`이 비면 기동 시 `RuntimeError("JWT_SECRET 환경 변수가 필요합니다")`로 종료합니다.

- 확인: `curl http://127.0.0.1:8000/healthz` → `{"status":"ok"}` (인증 없음). 로그인 후 `GET /api/health`가 구성요소 상태를 줍니다.
- **DB 경로**: 상대 경로(`data/backend.db`)는 실행 위치가 아니라 **저장소 루트** 기준입니다. `.env.example`의 `/data/...`는 compose용이라 Windows 로컬에서는 `C:\data`로 풀려 실패합니다. 로컬은 `data/shared.db`·`data/backend.db`를 쓰세요.
- **로컬 목 모드**: `ZABBIX_MOCK=true`(기본). 실서버 연결은 `ZABBIX_MOCK=false` + `ZABBIX_URL`·`ZABBIX_API_TOKEN`(토큰은 `.env`에만).
- 로컬에서 health를 부를 때 Agent·MCP를 띄우지 않았다면 `AGENT_URL`·`MCP_ZABBIX_URL`을 `http://127.0.0.1:...`로 두세요. 기본값은 compose 서비스 이름(`agent`·`mcp-zabbix`)이라 로컬에서는 이름 조회에 1초 넘게 걸릴 수 있습니다(다른 API는 영향 없음).

## 테스트

```powershell
uv run ruff check . ; uv run ruff format --check . ; uv run pytest -q
uv run pytest -m safety_regression -q   # 안전 회귀 세트(쓰기 금지·인증·메일 dedup 등 안전 규칙)
uv run pytest backend -q -k <키워드>      # backend 만, 일부만
```

- 테스트는 임시 DB와 `ZABBIX_MOCK=true`로 돕니다.
- (PR 90 머지 후) 테스트 환경은 `ZABBIX_URL`·`ZABBIX_API_TOKEN`·`ZABBIX_VERIFY_TLS`를 빈 값으로 고정해서, 저장소 루트의 `.env`에 실서버 값이 있어도 실제 Zabbix를 부르지 않습니다.
- (PR 94·102 머지 후) 계약과 어긋나면 깨지는 테스트가 생깁니다(`contracts/api.md`·`agent-api.md`의 표·예시를 직접 읽음).

## 환경 변수

값은 `.env`(루트)나 셸에서만 받습니다. 비밀값(`JWT_SECRET`·`*_PASSWORD`·`ZABBIX_API_TOKEN`·`SMTP_PASSWORD`·`INTERNAL_TOKEN`)은 코드·로그·응답에 쓰지 않습니다.

| 이름 | 기본값 | 뜻 |
|---|---|---|
| `JWT_SECRET` | (필수) | 토큰 서명 비밀. 비면 기동 거부 |
| `JWT_EXPIRE_MIN` | `480` | 토큰 유효 시간(분, 8시간) |
| `DEMO_ADMIN_PASSWORD`·`DEMO_ONCALL_PASSWORD` | (없음) | 시드 계정 `admin`·`oncall`의 비밀번호. 비어 있으면 그 계정은 만들지 않음. **처음 만들 때만** 적용 |
| `BACKEND_DB_PATH`·`SHARED_DB_PATH` | `data/backend.db`·`data/shared.db` | DB 파일. 상대 경로는 저장소 루트 기준 |
| `DB_SCHEMA_PATH` | (루트의 `contracts/db-schema.sql`) | 스키마 파일 |
| `ZABBIX_MOCK` | `true` | `true`면 네트워크 없이 `zabbix_ro` 목 데이터 |
| `ZABBIX_URL`·`ZABBIX_API_TOKEN` | (없음) | 실서버 모드에서 필수(`.../api_jsonrpc.php`, 읽기 전용 토큰) |
| `ZABBIX_VERIFY_TLS` | (비움=검증 켬) | `false`·`0`·`no`·`off`면 인증서 검사 끔 |
| `AGENT_URL`·`MCP_ZABBIX_URL` | `http://agent:8100`·`http://mcp-zabbix:8200/mcp` | Agent 채팅 중계·health 확인 주소 |
| `ORCHESTRATOR_URL` | (비움) | [선택] 총괄(orchestrator) 읽기 중계(#26·#27) 주소. 예 `http://localhost:8001`. 비어 있으면 503 `ORCHESTRATOR_UNAVAILABLE` |
| `INTERNAL_TOKEN` | (비움) | [선택] Backend→Agent 공유 비밀 |
| `ANALYZE_MIN_SEVERITY` | `2` | 이 심각도 미만 장애는 분석 대상이 아님(`analysis.status` skipped/pending 구분) |
| `CORS_ORIGINS` | `http://localhost:5173` | 쉼표 구분 |
| `CHAT_STREAMING` | `true` | `false`면 채팅을 비스트리밍 JSON으로(탈출 규칙 1) |
| `CHAT_FIRST_EVENT_TIMEOUT_SEC` | `3` | Agent 첫 이벤트 한도. 넘으면 `AGENT_UNAVAILABLE` |
| `MAIL_PROVIDER`·`MAIL_RECIPIENTS`·`MAIL_FROM`·`APP_BASE_URL` | `console`·(비움)·(비움)·(비움) | 메일 워커. `APP_BASE_URL`이 비면 본문의 링크만 생략 |
| `MAIL_POLL_SEC` | `30` | 메일 워커 주기 |
| `SMTP_HOST`·`SMTP_PORT`·`SMTP_USER`·`SMTP_PASSWORD` | `smtp.gmail.com`·`587`·(비움)·(비움) | `MAIL_PROVIDER=smtp`일 때 |

아래는 아직 머지되지 않은 PR에서 들어오는 설정입니다(머지되면 위 표와 같이 `.env` 변경 없이 기본값으로 동작).

| 이름 | 기본값 | 뜻 | 들어오는 PR |
|---|---|---|---|
| `ZABBIX_TIMEOUT_SEC` | `5` | API 5번·6번이 Zabbix를 기다리는 한도(health는 3초) | 112 |
| `ZABBIX_CACHE_TTL_SEC`·`ZABBIX_FAILURE_TTL_SEC` | `5`·`2` | Zabbix 응답(성공·실패) 재사용 시간 | 112 |
| `ZABBIX_MOCK_SCENARIO` | `demo` | 목 모드 상황(`default`·`demo`·`quiet`·`host_down`·`empty`·`outage`) | 113(→99) |
| `CHAT_KEEPALIVE_SEC` | `15` | Agent가 조용할 때 SSE `: ping` 주석을 보내는 간격 | 107 |

## 코드 지도

| 위치 | 하는 일 |
|---|---|
| `dejafix_backend/main.py` | 앱 조립·기동(스키마 적용·시드 계정). 메일 워커 기동 연결은 PR 86 머지 후 |
| `routers/` | API 8개(`auth`·`health`·`dashboard`·`problems`·`incidents`·`chat`) + [선택] `orchestrator`(총괄 읽기 중계 #26·#27, `contracts/api.md` 6장) |
| `db.py`·`deps.py` | DB 연결(shared 읽기 전용 ATTACH)·현재 사용자·역할 검사 |
| `mail/` | 메일 워커(리포트당 수신자별 1회, 재시도, 본문 7항목) |
| `envelope.py`·`errors.py` | 응답 봉투·오류 형식 |
