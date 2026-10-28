-- =====================================================================
-- DejaFix DB 스키마 v0 (contracts/db-schema.sql)
-- 소유자: DB·메일 담당 / 승인: Backend 담당 + 팀장(Agent)
-- 원본: docs/plan.md 5-1·5-2·5-3, docs/requirements.md DR-001~019, FR-DATA-001~005
-- 범위: [필수] 11 테이블만 (shared 9 + backend 2). [선택] plan_reviews·audit_logs·
--       notification_recipients, [이후] hosts_snapshot·metrics_daily 는 그 단계에서 추가한다.
--
-- 규칙
-- 1. 모든 문장은 IF NOT EXISTS (멱등). 기동할 때마다 다시 실행해도 오류가 없어야 한다.
-- 2. MVP 중 ALTER 금지. 스키마가 바뀌면 개발 DB를 지우고 다시 만든다 (NFR-MAINT-009).
-- 3. 이 파일은 두 DB를 함께 담는다. "-- @db shared" 줄부터 다음 "-- @db" 줄 전까지는
--    shared.db, "-- @db backend" 이후는 backend.db 에만 적용한다.
--      shared.db  : Agent·Scheduler 가 기동 시 shared 구역을 실행
--      backend.db : Backend 가 기동 시 backend 구역을 실행
--    구역을 섞어 실행하면 backend.db 안에 빈 incidents 같은 그림자 테이블이 생겨
--    ATTACH 한 shared.incidents 대신 잘못 읽힌다. 반드시 구역별로 실행한다.
-- 4. 연결마다 PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON; (DR-019)
--    PRAGMA 는 연결 설정이라 이 파일에 넣지 않는다. 적용 모듈이 연결 직후 실행한다.
-- 5. 시각은 전부 UTC ISO8601 문자열 'YYYY-MM-DDTHH:MM:SSZ' (DR-017). 화면만 KST.
-- 6. 테이블마다 쓰는 컴포넌트는 하나 (DR-002). 각 테이블 위 주석의 "작성자" 외에는 쓰지 않는다.
--    Backend 는 shared.db 를 ATTACH 'file:...shared.db?mode=ro' AS shared 로 읽기만 한다.
--    이때 backend.db 연결은 URI 모드로 열어야 한다: sqlite3.connect("file:/data/backend.db", uri=True).
--    URI 모드가 아니면 ATTACH 의 ?mode=ro 를 해석하지 못해 "unable to open database" 가 난다.
-- 7. *_json 컬럼은 JSON 문자열. 형식은 각 컬럼 주석과 contracts/agent-api.md 를 따른다.
--    API 응답 필드 이름은 컬럼 이름에서 _json 을 뗀 이름과 같다 (예: causes_json → causes).
-- =====================================================================


-- @db shared
-- =====================================================================
-- shared.db — 구조도의 공유 데이터 저장소
-- =====================================================================

-- ---------- Scheduler 소유 ----------

-- 작성자: Scheduler (problem.get 폴링). 읽기: Backend, Agent
-- API 매핑: #10·#11 incident 객체 (contracts/incident.schema.json)
--   id→id, zabbix_eventid/zabbix_triggerid/hostid→zabbix{eventid,triggerid,hostid},
--   hostid/host_name→host{id,name}, severity→severity{level,label}(라벨은 Backend 가 붙임),
--   tags_json→tags[]. analysis{status,report_id,plan_id} 는 저장 컬럼이 아니라 응답 시 JOIN.
CREATE TABLE IF NOT EXISTS incidents (
  id               INTEGER PRIMARY KEY,
  zabbix_eventid   TEXT    NOT NULL UNIQUE,                 -- problem.eventid, 중복 INSERT 방지
  zabbix_triggerid TEXT    NOT NULL,                        -- problem.objectid
  hostid           TEXT,                                    -- trigger.get selectHosts 로 보강
  host_name        TEXT,
  title            TEXT    NOT NULL,                        -- problem.name
  severity         INTEGER NOT NULL CHECK (severity BETWEEN 0 AND 5),   -- Zabbix 0~5
  status           TEXT    NOT NULL CHECK (status IN ('problem','resolved')),
  started_at       TEXT    NOT NULL,                        -- problem.clock
  resolved_at      TEXT,                                    -- r_clock
  acknowledged     INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0,1)),
  tags_json        TEXT    NOT NULL DEFAULT '[]',           -- [{"tag":"component","value":"cpu"}]
  first_seen_at    TEXT    NOT NULL,                        -- DejaFix 가 처음 본 시각
  last_seen_at     TEXT    NOT NULL                         -- 마지막 폴링에서 본 시각
);
CREATE INDEX IF NOT EXISTS ix_incidents_status  ON incidents(status, severity);
CREATE INDEX IF NOT EXISTS ix_incidents_started ON incidents(started_at);   -- #10 최신순 정렬

-- 작성자: Scheduler. 읽기: Backend (#4 scheduler_last_ok = poll_problems.last_ok_at)
-- [필수] 행은 job='poll_problems' 1개 (AS-M03). 매 주기 UPSERT.
CREATE TABLE IF NOT EXISTS scheduler_jobs (
  job          TEXT PRIMARY KEY,                            -- poll_problems ([이후] daily_collect, retention)
  last_run_at  TEXT,
  last_ok_at   TEXT,
  status       TEXT CHECK (status IS NULL OR status IN ('ok','error')),
  message      TEXT                                         -- 마지막 오류 요약 (비밀값 금지)
);

-- ---------- Agent 소유 ----------

-- 작성자: Agent. 읽기: Backend (#10·#11 analysis.status 계산)
-- status 흐름: queued → collecting → analyzing → validating → reported → planning → done
--   LLM 미설정·실패·타임아웃은 failed 가 아니라 done + error 에 사유 (FR-AG-002, AS-M11)
--   error 값: LLM_NOT_CONFIGURED | LLM_TIMEOUT | LLM_ERROR | LLM_BUDGET | PLAN_FAILED | 기타 사유
--   failed 는 리포트를 하나도 저장하지 못한 경우만.
CREATE TABLE IF NOT EXISTS agent_runs (
  id              TEXT    PRIMARY KEY,                      -- 'r_' + uuid
  kind            TEXT    NOT NULL CHECK (kind IN ('analyze','plan','chat')),
  incident_id     INTEGER REFERENCES incidents(id),
  conversation_id TEXT,                                     -- kind='chat' 일 때
  caller          TEXT    NOT NULL,                         -- worker | backend | claude | agent:<name>
  requested_by    INTEGER,                                  -- backend.db users.id (파일이 달라 FK 없음)
  status          TEXT    NOT NULL CHECK (status IN
                    ('queued','collecting','analyzing','validating','reported','planning','done','failed')),
  model           TEXT,                                     -- 실제 사용 모델, 가짜 LLM 은 'fake', LLM 없음은 NULL
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  tokens_in       INTEGER,                                  -- [선택] 토큰·비용 기록
  tokens_out      INTEGER,
  cost_usd        REAL,
  error           TEXT,
  started_at      TEXT    NOT NULL,
  finished_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_agent_runs_incident ON agent_runs(incident_id, kind, started_at);

-- 작성자: Agent. 읽기: Backend (#11 evidence[])
-- = 근거(Evidence). 리포트·계획·채팅의 evidence_ids 가 이 id 를 가리킨다 (SAFE-08·12).
-- API 매핑 #11 evidence[]: id, tool, args(args_json), ok(0/1→bool), duration_ms,
--   result_summary, data_clock, called_at. result_json 은 응답에 넣지 않는다.
CREATE TABLE IF NOT EXISTS tool_calls (
  id             TEXT    PRIMARY KEY,                       -- 'ev_' + 짧은 id
  run_id         TEXT    NOT NULL REFERENCES agent_runs(id),
  seq            INTEGER NOT NULL,                          -- run 안에서 호출 순서
  tool           TEXT    NOT NULL,                          -- MCP 도구 이름 (contracts/mcp-tools.md)
  args_json      TEXT    NOT NULL DEFAULT '{}',
  ok             INTEGER NOT NULL CHECK (ok IN (0,1)),      -- 실패한 호출도 ok=0 으로 남긴다
  duration_ms    INTEGER,
  result_summary TEXT,                                      -- 화면 표시용 한 줄
  result_json    TEXT,                                      -- 최대 32KB 로 잘라 저장
  data_clock     TEXT,                                      -- 결과 데이터의 수집 시각(가장 최근 값)
  called_at      TEXT    NOT NULL,
  UNIQUE (run_id, seq)
);

-- 작성자: Agent. 읽기: Backend (#11 report, 메일 워커)
-- 같은 장애를 다시 분석하면 version +1. 화면·메일은 최신 version 을 쓴다.
-- JSON 형식 (contracts/agent-api.md 2장 리포트 스키마와 같음)
--   impact_json      {"hosts":[str], "services":[str], "user_impact":str|null, "evidence_ids":[str]}
--   causes_json      [{"rank":1,"title":str,"confidence":"low|medium|high","reasoning":str,
--                      "evidence_ids":[str],"verify":str}]  최대 3개, 퍼센트·점수 금지 (SAFE-11)
--   facts_json       [{"label":str,"value":number|str|null,"unit":str|null,
--                      "unknown_reason":null|"NO_DATA|STALE|TOOL_ERROR|NO_PERMISSION|NOT_COLLECTED",
--                      "evidence_ids":[str],"collected_at":str|null}]
--                    value 가 null 이면 unknown_reason 필수, 값이 있으면 evidence_ids 필수 (SAFE-08)
--   unknowns_json    [{"label":str,"reason":"NO_DATA|STALE|TOOL_ERROR|NO_PERMISSION|NOT_COLLECTED"}]
--   next_checks_json [str]  사람이 확인할 것 (읽기 전용 확인)
CREATE TABLE IF NOT EXISTS analysis_reports (
  id               INTEGER PRIMARY KEY,
  incident_id      INTEGER NOT NULL REFERENCES incidents(id),
  run_id           TEXT    NOT NULL REFERENCES agent_runs(id),
  version          INTEGER NOT NULL CHECK (version >= 1),
  kind             TEXT    NOT NULL CHECK (kind IN ('llm','fallback')),
  summary          TEXT    NOT NULL,
  impact_json      TEXT    NOT NULL DEFAULT '{}',
  causes_json      TEXT    NOT NULL DEFAULT '[]',
  facts_json       TEXT    NOT NULL DEFAULT '[]',
  unknowns_json    TEXT    NOT NULL DEFAULT '[]',
  next_checks_json TEXT    NOT NULL DEFAULT '[]',
  created_at       TEXT    NOT NULL,
  UNIQUE (incident_id, version)
);
CREATE INDEX IF NOT EXISTS ix_reports_created ON analysis_reports(created_at);  -- #5 오늘 리포트 수, 메일 워커

-- 작성자: Agent. 읽기: Backend (#11 plan)
-- 실행 모드 자체가 없다. mode 는 'preview' 외 값을 넣으면 INSERT 가 실패한다 (SAFE-04).
-- max_tier 는 코드가 plan_steps 의 최고 티어로 계산 (C > B > A).
CREATE TABLE IF NOT EXISTS change_plans (
  id               INTEGER PRIMARY KEY,
  incident_id      INTEGER REFERENCES incidents(id),
  report_id        INTEGER REFERENCES analysis_reports(id),
  run_id           TEXT    NOT NULL REFERENCES agent_runs(id),
  title            TEXT    NOT NULL,
  goal             TEXT,
  mode             TEXT    NOT NULL DEFAULT 'preview' CHECK (mode = 'preview'),
  max_tier         TEXT    NOT NULL CHECK (max_tier IN ('A','B','C')),
  assumptions_json TEXT    NOT NULL DEFAULT '[]',           -- [str]
  created_at       TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_change_plans_incident ON change_plans(incident_id, id);

-- 작성자: Agent (PLANNING, 코드만). 읽기: Backend (#11 steps[])
-- tier 는 packs/<domain>/actions.yaml 매칭으로 코드가 정한 값만 저장 (LLM 티어 무시, 미등록 → C).
-- B 는 precheck·rollback 이 둘 다 있어야 하고, 없으면 C 로 강등하고 rationale 에 사유 (SAFE-06·07).
-- B 규칙은 Agent 코드가 강제하고 안전 테스트로 확인한다. 아래 CHECK 는 마지막 방어선이다.
-- API 매핑 #11 steps[]: evidence_ids_json → evidence_ids, 나머지는 컬럼 이름 그대로.
CREATE TABLE IF NOT EXISTS plan_steps (
  id                INTEGER PRIMARY KEY,
  plan_id           INTEGER NOT NULL REFERENCES change_plans(id),
  seq               INTEGER NOT NULL,
  action_id         TEXT,                                   -- actions.yaml 의 id, 없으면 NULL (→ C)
  title             TEXT    NOT NULL,
  target            TEXT,                                   -- 대상 호스트·경로
  command_preview   TEXT,                                   -- 보여주기만 하는 명령 예시
  tier              TEXT    NOT NULL CHECK (tier IN ('A','B','C')),
  rationale         TEXT,                                   -- 티어 근거·강등 사유
  precheck          TEXT,
  expected_effect   TEXT,
  risk              TEXT,
  rollback          TEXT,
  evidence_ids_json TEXT    NOT NULL DEFAULT '[]',
  UNIQUE (plan_id, seq),
  CHECK (tier <> 'B' OR (precheck IS NOT NULL AND precheck <> ''
                         AND rollback IS NOT NULL AND rollback <> ''))
);

-- 작성자: Agent. 읽기: Backend ([선택] #19 대화 목록)
CREATE TABLE IF NOT EXISTS conversations (
  id          TEXT    PRIMARY KEY,                          -- 'c_' + uuid
  user_id     INTEGER,                                      -- backend.db users.id (FK 없음)
  caller      TEXT    NOT NULL DEFAULT 'backend',
  incident_id INTEGER REFERENCES incidents(id),             -- 장애 상세에서 연 대화
  title       TEXT,
  created_at  TEXT    NOT NULL,
  updated_at  TEXT    NOT NULL
);

-- 작성자: Agent. 읽기: Backend ([선택] #19 메시지)
-- assistant 메시지의 근거는 run_id → tool_calls 로 연결한다.
CREATE TABLE IF NOT EXISTS messages (
  id              INTEGER PRIMARY KEY,
  conversation_id TEXT    NOT NULL REFERENCES conversations(id),
  role            TEXT    NOT NULL CHECK (role IN ('user','assistant')),
  content         TEXT    NOT NULL,
  run_id          TEXT    REFERENCES agent_runs(id),
  created_at      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_conversation ON messages(conversation_id, id);


-- @db backend
-- =====================================================================
-- backend.db — Backend 전용 저장소 (작성자·읽기 모두 Backend)
-- =====================================================================

-- 시드: admin(admin), oncall(operator). 비밀번호는 .env DEMO_ADMIN_PASSWORD·DEMO_ONCALL_PASSWORD
-- 로 Backend 가 기동 시 만든다. 이 파일에 시드 행이나 해시를 넣지 않는다.
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY,
  username      TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,                              -- bcrypt/argon2, 평문 금지
  display_name  TEXT,
  email         TEXT,
  role          TEXT NOT NULL CHECK (role IN ('admin','operator','viewer')),
  created_at    TEXT NOT NULL,
  last_login_at TEXT
);

-- 작성자: Backend 메일 워커. 읽기: Backend (#11 mail_logs[])
-- 자동 발송은 dedup_key = 'auto:' || report_id || ':' || recipient → 리포트당 수신자별 1통 (SAFE-16)
-- 수신자는 .env MAIL_RECIPIENTS 에서만 온다.
-- API 매핑 #11 mail_logs[]: id, kind, recipient, status, attempts, error, created_at, sent_at
CREATE TABLE IF NOT EXISTS mail_logs (
  id           INTEGER PRIMARY KEY,
  kind         TEXT    NOT NULL CHECK (kind IN ('incident_report','manual','test')),
  incident_id  INTEGER,                                     -- shared.incidents.id (FK 없음)
  report_id    INTEGER,                                     -- shared.analysis_reports.id (FK 없음)
  recipient    TEXT    NOT NULL,
  subject      TEXT    NOT NULL,
  provider     TEXT    NOT NULL CHECK (provider IN ('smtp','sendgrid','console')),
  status       TEXT    NOT NULL CHECK (status IN ('sent','failed','skipped')),
  attempts     INTEGER NOT NULL DEFAULT 1 CHECK (attempts >= 0),
  error        TEXT,                                        -- 비밀값·전체 스택 금지
  dedup_key    TEXT    UNIQUE,
  requested_by INTEGER REFERENCES users(id),                -- 수동·테스트 발송 요청자 ([선택])
  created_at   TEXT    NOT NULL,
  sent_at      TEXT
);
CREATE INDEX IF NOT EXISTS ix_mail_logs_incident ON mail_logs(incident_id, id);

-- [이후] 해결 메모 (Issue #153, FR-RAG-010). 작성자: Backend (POST /api/incidents/{id}/notes), 사람만 쓴다.
-- 읽기: Backend (GET), libs/kb 색인기(backend.db 를 mode=ro 로만 읽음).
-- incident_id 는 다른 DB(shared.incidents.id)라 FK 없이 앱에서 존재 확인. 수정 이력 없음(created_at 하나).
CREATE TABLE IF NOT EXISTS resolution_notes (
  id             INTEGER PRIMARY KEY,
  incident_id    INTEGER NOT NULL,          -- shared.incidents.id
  author_user_id INTEGER NOT NULL REFERENCES users(id),
  root_cause     TEXT,                      -- 사람이 쓴 실제 원인
  action_taken   TEXT,                      -- 한 조치 (실행은 사람이 시스템 밖에서 함)
  result         TEXT,                      -- 결과
  created_at     TEXT NOT NULL              -- UTC ISO8601
);
