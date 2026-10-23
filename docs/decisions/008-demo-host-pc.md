# 008 데모 호스트 이름·데모 PC — `Heon-PC`, 주입은 Zabbix·MCP 담당 (FR-ZBX-003)
- 결정: 데모 PC는 Zabbix·MCP 담당(재헌) PC, Zabbix 호스트 이름은 **`Heon-PC`**(장치 이름 DESKTOP-86DNGIH, 에이전트 7.4.15)로 한다. 데모 당일 `inject-cpu.ps1 -Minutes 3` 주입은 재헌이 이 PC에서 한다. 기획서의 후보 `LAB-PC-DEMO`와 예전 표기 `HEONGAMINGPC`는 쓰지 않는다. 멘토 점검 시각·차별점 장면 채택은 이 기록에서 정하지 않고 TODO로 남긴다.
- 이유: 10/16 리허설 2회(15:38·15:45)가 이 호스트에서 주입→메일 2분 27초·1분 35초로 3분 이내 2회 연속(NFR-PERF-001)을 충족했고, 트리거도 112초·72초로 결정 016 목표(120초) 안이다. 데모 직전에 호스트 이름을 바꾸면 Zabbix 호스트·트리거 식(`avg(/<호스트>/...)`) 재적용과 재측정이 필요하다.
- 대안(기각): ① `LAB-PC-DEMO`로 이름 변경 — 재적용·재측정 부담 ② 팀장 PC(TaeYoon-PC) — 115초로 목표 안이지만 데모 PC 측정이 아니고 발표 진행과 겹친다.
- 결정자·일시 / 근거: 팀장(이태윤), 2026-10-23 KST / Issue #124, `docs/demo/rehearsal-log.md` 2·3회차, 결정 016, `docs/requirements.md` FR-ZBX-003(동결 문서라 고치지 않음)
