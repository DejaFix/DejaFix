# scheduler

## 역할
- [필수] `INCIDENT_POLL_SEC`(30초)마다 `problem.get(recent=true)` → 새 `eventid`는 `incidents` INSERT, `r_eventid`가 생기면 `resolved` 처리 (FR-SCH-001~003)
- [필수] `problem.get`은 호스트를 안 주므로 `trigger.get(selectHosts)`로 `hostid`·`host_name` 보강
- [필수] 매 주기 `scheduler_jobs`의 `poll_problems` 1행 UPSERT(`last_run_at, last_ok_at, status, message`), 실패해도 죽지 않고 다음 주기 재시도 (FR-SCH-004·009)
- [필수] 기동 시 `contracts/db-schema.sql`(전 문장 `IF NOT EXISTS`)을 `shared.db`에 적용
- [이후] 일일 지표 요약·사양 수집·보관 정리 — 지금 만들지 않는다

## 하지 않는 것
- Agent·Backend·LLM 호출 (구조도에 없는 화살표)
- 자기 테이블(`incidents`, `scheduler_jobs`) 밖 쓰기, `backend.db` 접근
- Zabbix 직접 HTTP 호출 — 반드시 `libs/zabbix_ro` 경유

## 의존 계약
- `contracts/db-schema.sql`, `contracts/incident.schema.json`

## 실행
- 로컬: `uv run --package scheduler python -m dejafix_scheduler` (패키지 이름 `dejafix_scheduler` — 폴더 이름과 같으면 pytest importlib 모드에서 가려짐)
- 환경 변수: `SHARED_DB_PATH`, `INCIDENT_POLL_SEC`(기본 30, 최소 5), `ZABBIX_MOCK`(true면 `dejafix_scheduler/fixtures/mock_zabbix.json`), `SCHEDULER_MOCK_FILE`(목 파일 경로 바꿀 때)
- 실서버 모드는 `libs/zabbix_ro`의 `from_env()`·`client.call(method, params)`를 쓴다. 아직 없으면 매 주기 `scheduler_jobs.poll_problems.status='error'`로 남기고 계속 돈다

## 테스트
- `uv run pytest scheduler` — `ZABBIX_MOCK=true` fixture로 INSERT·중복 방지·resolved 전이·호스트 보강·실패 재시도·`scheduler_jobs` (FR-SCH-001~005·009)

## 작업 완료 체크
작업 단위는 `docs/work-order.md`의 T 번호(Scheduler·DB: T06·T07, T35~T37, T41, T64). 끝나서 PR이 dev에 머지되면 노션 「DejaFix 작업 진행 현황」 현황표에서 그 행을 **`완료`로 체크**한다(사람이). 세션은 끝날 때 완료할 T 번호를 알려 준다.
