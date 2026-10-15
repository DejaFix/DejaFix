# PLAN-scheduler-db — Scheduler·공유 스키마·메일 워커 작업 큐 (담당 DB·메일 담당, 부 Backend 담당 / 폴더 `scheduler/`, `backend/` 안 메일 모듈)

- 기준: `scheduler/CLAUDE.md`, `backend/CLAUDE.md` "메일 워커", `docs/mvp-checklist.md` "Scheduler"·"데이터"·메일 줄, `contracts/db-schema.sql`(DB·메일 담당 소유)
- 항목마다 `uv run ruff check . && uv run ruff format --check . && uv run pytest` 통과 후 커밋 1개. 실패 2번이면 `[BLOCKED]` + `LOG-scheduler-db.md`
- 개발 기본: `ZABBIX_MOCK=true`, `MAIL_PROVIDER=console`. 야간에는 실 Zabbix·실발송 금지
- `backend/`에서는 **메일 모듈 파일만** 만진다(API 코드는 PLAN-backend). 겹치는 파일이 생기면 LOG에 적고 중단

## 작업 큐
- [ ] **1. 공유 스키마 멱등 적용 모듈** (FR-DATA-003·004·005, DR-016·019): `contracts/db-schema.sql`을 읽어 `shared.db`에 실행(전 문장 `IF NOT EXISTS`), 연결마다 `PRAGMA journal_mode=WAL; busy_timeout=5000; foreign_keys=ON`. Agent도 같은 모듈을 쓰도록 `libs/`에 두거나 복제 최소화. **테스트: 두 번 연속 적용 오류 없음, `sqlite_master`에 shared 9 테이블, `change_plans.mode`에 `'preview'` 외 값 INSERT 실패**
- [ ] **2. Scheduler 골격·설정**: `INCIDENT_POLL_SEC`(기본 30), `SHARED_DB_PATH`, `ZABBIX_*` 읽기, `libs/zabbix_ro` 클라이언트 생성, 메인 루프(예외로 죽지 않음)
- [ ] **3. Problem 폴링 → `incidents` INSERT** (FR-SCH-001·003, DR-003): `problem.get(recent=true)` → 새 `eventid`만 INSERT(`zabbix_eventid` UNIQUE), `trigger.get(triggerids, selectHosts)`로 `hostid`·`host_name` 보강, `severity, title, started_at(UTC ISO8601), tags_json, first_seen_at, last_seen_at`. **테스트(fixture): 두 번 폴링해도 행 1개, `hostid`·`host_name` not null**
- [ ] **4. 해결 처리** (FR-SCH-002): `r_eventid`/`r_clock`이 생기면 `status='resolved'`, `resolved_at`, `last_seen_at` 갱신. 테스트: fixture 전이
- [ ] **5. 재시도·`scheduler_jobs`** (FR-SCH-004·009, NFR-OBS-004): 매 주기 `poll_problems` 1행 UPSERT(`last_run_at, last_ok_at, status, message`). Zabbix 실패 시 오류 로그 + `status='error'`, 프로세스 생존, 복구 후 `ok`. 테스트: 예외 2주기 주입
- [ ] **6. 메일 워커 골격** (FR-MAIL-001·007, DR-012): Backend 앱의 백그라운드 태스크, 30초 주기, `shared.analysis_reports` ↔ `backend.mail_logs` 비교로 미발송 리포트 선정, `MAIL_PROVIDER=console`이면 로그 출력 + `mail_logs(provider='console', status='sent')` 기록
- [ ] **7. 수신자·dedup·재시도** (FR-MAIL-002·003·004, SAFE-16): 수신자는 `MAIL_RECIPIENTS`만, `dedup_key='auto:'+report_id+':'+recipient` UNIQUE, 실패 3회 후 `failed`+`attempts`+`error`, 워커 지속. **테스트: 같은 리포트에 워커 3회 → 수신자당 1행(머지 조건), SMTP 차단 → `attempts=3`·`failed`**
- [ ] **8. 메일 제목·본문 템플릿** (FR-MAIL-005): 제목 `[DejaFix][<심각도>] <host_name> - <제목>`, 평문 본문 7항목(종류·요약·원인 TOP3·확인할 수 없음·계획 단계 수·최고 티어+"미리보기 — 실행되지 않음"·`APP_BASE_URL/incidents/{id}`·시각 KST). 값은 저장된 리포트·계획에서 그대로(문장 생성 금지)
- [ ] **9. SMTP·SendGrid 공급자** (FR-MAIL-006, [선택] FR-MAIL-008): `smtp.gmail.com:587` STARTTLS + 앱 비밀번호 구현(실발송은 낮에 사람이), `sendgrid`는 스위치 자리만. 발신 계정 `(TODO: 추후결정)`
- [ ] **10. `infra/scripts/backup-db.ps1`** (FR-INF-006, DR-020): SQLite 백업 API로 `shared.db`·`backend.db` → `backups/<name>-<ts>.db`, 최근 5개 보관, 복원 절차 주석. (`infra/scripts/`는 Zabbix·MCP 담당 폴더 — 이 파일 1개만 DB·메일 담당 소유로 합의됨, 10-1)
- [ ] **11. 마무리**: Scheduler 코드에 `agent_runs` 등 타 테이블 INSERT 없음(`rg`), 엔진 하드코딩 0건, 시각이 전부 UTC ISO8601 — LOG 기록
