# backend

FastAPI BFF (:8000, 내부 전용). 로그인(JWT)·화면용 API 8개·채팅 SSE 중계·메일 워커. `backend.db`에 쓰고 `shared.db`는 읽기 전용 ATTACH로만 읽는다. 화면 표시용 Zabbix 조회는 `libs/zabbix_ro`로 직접 하되 AI 판단용 조회는 하지 않는다. 분석 문장·원인·티어를 만들거나 바꾸지 않는다.

규칙·실행·테스트는 `CLAUDE.md`. 계약은 `contracts/api.md`·`contracts/incident.schema.json`(제공).
