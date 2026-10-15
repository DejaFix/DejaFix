# libs/shared_db — 공유 DB(shared.db) 스키마 적용·연결 공용 모듈

> 내 라벨: to-agent. 작업 시작 시 `gh issue list --label to-agent --state open` 부터 확인 (`docs/agent-collaboration.md`)

담당: DB·메일 담당 (부 Backend 담당). 먼저 읽을 것: 루트 `CLAUDE.md` → `contracts/db-schema.sql` → 이 폴더 `README.md`.

- 하는 일: `contracts/db-schema.sql`을 `-- @db shared` / `-- @db backend` 구역별로 멱등 적용, 연결 PRAGMA(`journal_mode=WAL; busy_timeout=5000; foreign_keys=ON`) (T35, FR-DATA-003·004). 개발용 시드는 `fixtures/seed_dev.sql`
- 쓰는 곳: Agent·Scheduler(shared 구역), Backend(backend 구역). 스키마 원본은 이 폴더가 아니라 `contracts/db-schema.sql`이다
- 하지 않는 것: 스키마를 이 폴더에 복사하거나 고치기(계약 PR로만), `ALTER`, 구역을 섞어 적용하기
- 테스트: `uv run pytest libs/shared_db` — 두 번 연속 적용 오류 없음, shared 9·backend 2 테이블, `change_plans.mode`에 `'preview'` 외 값 거부
