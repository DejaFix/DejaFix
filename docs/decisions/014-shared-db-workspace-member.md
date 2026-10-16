# 014 공유 DB 스키마 모듈을 uv workspace 멤버(libs/shared_db)로 두고 Agent·Scheduler가 의존
- 결정: `contracts/db-schema.sql` 적용·연결 PRAGMA 코드는 `libs/shared_db`(패키지 `shared-db`) 한 곳에 두고, Agent·Scheduler는 `uv add --package <서비스> shared-db`로 연결해 기동 시 `open_db(SHARED_DB_PATH, "shared")`를 부른다. Backend 연결 여부는 Backend 담당이 정한다.
- 이유: 기획서 5-1·DR-016은 Agent·Scheduler가 둘 다 기동 시 같은 스키마를 멱등 적용하도록 정한다. 서비스마다 코드를 복사하면 스키마 적용 방식이 갈라진다.
- 대안(기각): 서비스별 복사(중복·불일치 위험), Scheduler만 적용(기동 순서 의존 — NFR-AVAIL-002 위반).
- 결정자·일시 / 근거: DB·메일 담당, 2026-10-15 / Issue #24, PR #21(T35)·#29(agent 연결)·Scheduler T36 PR, 기획서 13-2 멤버 목록에 `libs/shared_db` 추가
