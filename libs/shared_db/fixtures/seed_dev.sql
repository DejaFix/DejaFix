-- =====================================================================
-- 개발용 시드 데이터 (fixture). 데모·운영 DB에 넣지 않는다.
-- 목적: Agent 가 아직 없을 때 Backend #10·#11·#5·#4 와 메일 워커를 실제 DB 로 개발·검증
-- 전제: contracts/db-schema.sql 의 구역을 먼저 적용한 빈 DB
-- 사용법: libs/shared_db/README.md
--
-- 형식은 노션 「DejaFix 프론트 API 요청서」 #11 예시와 같고, 대표 장애만 금요일 데모에 맞춰 CPU 로 바꿨다.
-- action_id 는 예시값이다. 실제 동작 ID 는 packs/<domain>/actions.yaml 에서 온다.
-- 모든 INSERT 는 OR IGNORE 라 여러 번 실행해도 행이 늘지 않는다.
--
-- 장애 6건이 화면 analysis.status 6값을 하나씩 만든다 (contracts/agent-api.md 3-2)
--   1 CPU High       run done   + llm 리포트      → done     (계획 A·B·C 3단계, STALE 값, NOT_COLLECTED)
--   2 메모리 Average  run done   + fallback 리포트 → fallback (LLM_NOT_CONFIGURED, A 단계만)
--   3 디스크 High     run 없음                      → pending
--   4 정보 Info(1)    run 없음, 기준 미만           → skipped  (ANALYZE_MIN_SEVERITY 기본 2)
--   5 CPU High 해결   run analyzing                 → running  (resolved 장애도 분석, AS-M09)
--   6 네트워크 Warning run failed                    → failed
-- =====================================================================

-- @db shared

INSERT OR IGNORE INTO incidents
  (id, zabbix_eventid, zabbix_triggerid, hostid, host_name, title, severity, status,
   started_at, resolved_at, acknowledged, tags_json, first_seen_at, last_seen_at)
VALUES
  (1, '40301', '23601', '10584', 'LAB-PC-07', 'High CPU utilization (over 85% for 1m)', 4, 'problem',
   '2026-10-15T01:20:00Z', NULL, 0, '[{"tag":"component","value":"cpu"}]',
   '2026-10-15T01:20:20Z', '2026-10-15T01:25:20Z'),
  (2, '40302', '23602', '10585', 'LAB-PC-08', 'High memory utilization (>90% for 5m)', 3, 'problem',
   '2026-10-15T00:50:00Z', NULL, 0, '[{"tag":"component","value":"memory"}]',
   '2026-10-15T00:50:30Z', '2026-10-15T01:25:20Z'),
  (3, '40303', '23603', '10584', 'LAB-PC-07', 'Disk space is low (used > 80%) on C:', 4, 'problem',
   '2026-10-15T01:24:40Z', NULL, 0, '[{"tag":"component","value":"storage"}]',
   '2026-10-15T01:25:20Z', '2026-10-15T01:25:20Z'),
  (4, '40304', '23604', '10586', 'LAB-PC-09', 'Zabbix agent version changed', 1, 'problem',
   '2026-10-15T01:10:00Z', NULL, 0, '[]',
   '2026-10-15T01:10:20Z', '2026-10-15T01:25:20Z'),
  (5, '40305', '23601', '10585', 'LAB-PC-08', 'High CPU utilization (over 85% for 1m)', 4, 'resolved',
   '2026-10-15T01:05:00Z', '2026-10-15T01:15:00Z', 0, '[{"tag":"component","value":"cpu"}]',
   '2026-10-15T01:05:20Z', '2026-10-15T01:15:20Z'),
  (6, '40306', '23606', '10586', 'LAB-PC-09', 'Interface Ethernet: High bandwidth usage', 2, 'problem',
   '2026-10-14T22:00:00Z', NULL, 0, '[{"tag":"component","value":"network"}]',
   '2026-10-14T22:00:20Z', '2026-10-15T01:25:20Z');

INSERT OR IGNORE INTO scheduler_jobs (job, last_run_at, last_ok_at, status, message)
VALUES ('poll_problems', '2026-10-15T01:25:20Z', '2026-10-15T01:25:20Z', 'ok', NULL);

INSERT OR IGNORE INTO agent_runs
  (id, kind, incident_id, conversation_id, caller, requested_by, status, model,
   tool_call_count, error, started_at, finished_at)
VALUES
  ('r_seed1', 'analyze', 1, NULL, 'worker', NULL, 'done', 'fake', 4, NULL,
   '2026-10-15T01:20:30Z', '2026-10-15T01:21:10Z'),
  ('r_seed2', 'analyze', 2, NULL, 'worker', NULL, 'done', NULL, 4, 'LLM_NOT_CONFIGURED',
   '2026-10-15T00:50:40Z', '2026-10-15T00:51:05Z'),
  ('r_seed5', 'analyze', 5, NULL, 'worker', NULL, 'analyzing', NULL, 2, NULL,
   '2026-10-15T01:25:10Z', NULL),
  ('r_seed6', 'analyze', 6, NULL, 'worker', NULL, 'failed', NULL, 1, 'DB_WRITE_ERROR: 시드 예시',
   '2026-10-14T22:00:30Z', '2026-10-14T22:00:40Z');

-- 근거. ev_s3 은 오래된 값(STALE), ev_s7 은 실패한 호출(ok=0)
INSERT OR IGNORE INTO tool_calls
  (id, run_id, seq, tool, args_json, ok, duration_ms, result_summary, result_json, data_clock, called_at)
VALUES
  ('ev_s1', 'r_seed1', 1, 'zabbix_get_problem', '{"eventid":"40301"}', 1, 210,
   'High CPU utilization, 트리거 조건 1분 평균 > 85%', NULL, '2026-10-15T01:20:00Z', '2026-10-15T01:20:31Z'),
  ('ev_s2', 'r_seed1', 2, 'zabbix_get_host', '{"hostid":"10584"}', 1, 150,
   'LAB-PC-07, 가용, 유지보수 아님', NULL, '2026-10-15T01:20:31Z', '2026-10-15T01:20:32Z'),
  ('ev_s3', 'r_seed1', 3, 'zabbix_list_items', '{"hostid":"10584","key_search":"memory"}', 1, 188,
   '메모리 값이 40분 전 이후 갱신 안 됨 (stale)', NULL, '2026-10-15T00:40:00Z', '2026-10-15T01:20:33Z'),
  ('ev_s4', 'r_seed1', 4, 'zabbix_get_history', '{"itemid":"45123","time_from":"2026-10-15T00:20:00Z"}', 1, 412,
   '최근 1시간 CPU 사용률 최대 96.1%, 01:19 부터 85% 초과', NULL, '2026-10-15T01:19:30Z', '2026-10-15T01:20:35Z'),
  ('ev_s5', 'r_seed2', 1, 'zabbix_get_problem', '{"eventid":"40302"}', 1, 190,
   'High memory utilization, 5분 평균 > 90%', NULL, '2026-10-15T00:50:00Z', '2026-10-15T00:50:41Z'),
  ('ev_s6', 'r_seed2', 2, 'zabbix_get_history', '{"itemid":"45130","time_from":"2026-10-14T23:50:00Z"}', 1, 380,
   '최근 1시간 메모리 사용률 91~94%', NULL, '2026-10-15T00:50:00Z', '2026-10-15T00:50:43Z'),
  ('ev_s7', 'r_seed2', 3, 'zabbix_get_host', '{"hostid":"10585"}', 0, 5000,
   '조회 실패 (ZABBIX_ERROR, 타임아웃)', NULL, NULL, '2026-10-15T00:50:44Z'),
  ('ev_s8', 'r_seed2', 4, 'zabbix_list_items', '{"hostid":"10585","key_search":"memory"}', 1, 170,
   '메모리 사용률 최신값 93.2%', NULL, '2026-10-15T00:50:00Z', '2026-10-15T00:50:49Z');

INSERT OR IGNORE INTO analysis_reports
  (id, incident_id, run_id, version, kind, summary, impact_json, causes_json, facts_json,
   unknowns_json, next_checks_json, created_at)
VALUES
  (1, 1, 'r_seed1', 1, 'llm',
   'LAB-PC-07의 CPU 사용률이 최근 1시간 최대 96.1%로 임계값(85%)을 넘었습니다.',
   '{"hosts":["LAB-PC-07"],"services":[],"user_impact":"실습 프로그램 응답이 느려질 수 있음","evidence_ids":["ev_s4"]}',
   '[{"rank":1,"title":"특정 프로세스의 CPU 과다 사용","confidence":"medium","reasoning":"01:19부터 사용률이 급격히 올라 한 프로세스가 원인일 가능성이 있습니다.","evidence_ids":["ev_s4","ev_s1"],"verify":"작업 관리자에서 CPU 상위 프로세스 확인"},{"rank":2,"title":"백업 작업으로 인한 일시 증가","confidence":"low","reasoning":"백업 작업 여부는 수집되지 않아 판단 근거가 부족합니다.","evidence_ids":[],"verify":"백업 스케줄 확인"}]',
   '[{"label":"CPU 사용률 최대","value":96.1,"unit":"%","unknown_reason":null,"evidence_ids":["ev_s4"],"collected_at":"2026-10-15T01:19:30Z"},{"label":"메모리 사용률","value":null,"unit":"%","unknown_reason":"STALE","evidence_ids":["ev_s3"],"collected_at":"2026-10-15T00:40:00Z"}]',
   '[{"label":"백업 작업 여부","reason":"NOT_COLLECTED"},{"label":"같은 트리거 최근 7일 발생 횟수","reason":"NOT_COLLECTED"}]',
   '["CPU 상위 프로세스와 시작 시각 확인","메모리 수집이 멈춘 이유 확인"]',
   '2026-10-15T01:20:52Z'),
  (2, 2, 'r_seed2', 1, 'fallback',
   'LAB-PC-08의 메모리 사용률 최신값은 93.2%입니다. 원인은 확인할 수 없습니다.',
   '{"hosts":["LAB-PC-08"],"services":[],"user_impact":null,"evidence_ids":["ev_s8"]}',
   '[]',
   '[{"label":"메모리 사용률","value":93.2,"unit":"%","unknown_reason":null,"evidence_ids":["ev_s8"],"collected_at":"2026-10-15T00:50:00Z"},{"label":"호스트 가용성","value":null,"unit":null,"unknown_reason":"TOOL_ERROR","evidence_ids":["ev_s7"],"collected_at":null}]',
   '[{"label":"원인","reason":"NOT_COLLECTED"}]',
   '["메모리 상위 프로세스 확인"]',
   '2026-10-15T00:51:00Z');

INSERT OR IGNORE INTO change_plans
  (id, incident_id, report_id, run_id, title, goal, mode, max_tier, assumptions_json, created_at)
VALUES
  (1, 1, 1, 'r_seed1', 'LAB-PC-07 CPU 부하 대응 계획', 'CPU 사용률을 85% 아래로', 'preview', 'C',
   '["CPU 상위 프로세스는 업무 필수 프로그램이 아님"]', '2026-10-15T01:21:05Z'),
  (2, 2, 2, 'r_seed2', 'LAB-PC-08 메모리 확인 계획', NULL, 'preview', 'A',
   '[]', '2026-10-15T00:51:02Z');

INSERT OR IGNORE INTO plan_steps
  (id, plan_id, seq, action_id, title, target, command_preview, tier, rationale, precheck,
   expected_effect, risk, rollback, evidence_ids_json)
VALUES
  (1, 1, 1, 'seed_check_process_list', 'CPU 상위 프로세스 확인', 'LAB-PC-07',
   'Get-Process | Sort-Object CPU -Descending | Select-Object -First 5', 'A',
   '규칙: actions.yaml 조회 동작 (시드 예시)', NULL, '원인 프로세스 확인', '없음 (조회)', NULL, '["ev_s4"]'),
  (2, 1, 2, 'seed_stop_batch_job', '부하 배치 작업 일시 중지', 'LAB-PC-07 예약 작업',
   'Disable-ScheduledTask -TaskName <작업 이름>', 'B',
   '규칙: actions.yaml 변경 동작, precheck·rollback 있음 (시드 예시)',
   '작업 이름과 다음 실행 시각 확인', 'CPU 사용률 감소 예상', '예약 작업이 한 번 건너뛰어짐',
   'Enable-ScheduledTask -TaskName <작업 이름>', '["ev_s4"]'),
  (3, 1, 3, NULL, '서버 재부팅', 'LAB-PC-07',
   'Restart-Computer', 'C',
   'actions.yaml 미등록 동작 → C 로 지정 (SAFE-06)', NULL, NULL, '서비스 중단', NULL, '[]'),
  (4, 2, 1, 'seed_check_process_list', '메모리 상위 프로세스 확인', 'LAB-PC-08',
   'Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 5', 'A',
   '규칙 기반 계획: fallback_plans.mem (시드 예시)', NULL, '원인 프로세스 확인', '없음 (조회)', NULL, '["ev_s8"]');

-- @db backend

INSERT OR IGNORE INTO mail_logs
  (id, kind, incident_id, report_id, recipient, subject, provider, status, attempts, error,
   dedup_key, requested_by, created_at, sent_at)
VALUES
  (1, 'incident_report', 1, 1, 'oncall@example.com',
   '[DejaFix][High] LAB-PC-07 - High CPU utilization (over 85% for 1m)', 'console', 'sent', 1, NULL,
   'auto:1:oncall@example.com', NULL, '2026-10-15T01:20:55Z', '2026-10-15T01:20:58Z'),
  (2, 'incident_report', 2, 2, 'oncall@example.com',
   '[DejaFix][Average] LAB-PC-08 - High memory utilization (>90% for 5m)', 'smtp', 'failed', 3,
   'SMTP 연결 실패 (시드 예시)', 'auto:2:oncall@example.com', NULL, '2026-10-15T00:51:10Z', NULL);
