# 019 DejaFix 하나가 회사마다 그 회사 Zabbix를 본다 (018 대안 ③ 채택)
- 결정: DejaFix는 AXcellent 한 벌에 든 인프라 에이전트다. AXcellent의 다른 AI처럼 서버 하나가 회사마다 그 회사 관리자가 넣은 Zabbix를 보고, 장애·리포트·계획·대화·메일·지식 검색도 회사별로 나눈다. 회사는 AXcellent dejafix-proxy가 붙이는 요청 머리 `X-AX-Company`(로그인 세션의 회사)로 정하고, DejaFix는 거른 회사를 응답 머리 `X-DejaFix-Company`로 돌려준다. 머리는 `COMPANY_HEADER_ACCOUNTS`에 적은 프록시 계정만 따르고, 사람이 직접 로그인한 계정은 자기 `users.company_id`(비면 기본 회사)로 고정이다. 그 회사에 Zabbix 연결이 없으면 다른 회사 것으로 떨어지지 않고 빈 상태("Zabbix 연결 전")다. 머리가 없으면 기본 회사(`DEFAULT_COMPANY_ID`, AXcellent 회사 ID와 같은 값)이고, `DEFAULT_COMPANY_ID`가 없으면 회사 나누기가 꺼져 지금처럼 동작한다(echo 머리도 없음). 자동 메일은 당장 기본 회사 장애만 보낸다(수신자 한 벌). 이관은 표를 다시 만들어 데이터를 지우지 않는다(`db-schema.sql` 규칙 8). 장애는 (회사, Zabbix 연결 구분값, eventid)로 가르고, 회사가 Zabbix를 바꾸면 옛 연결의 열린 장애를 `connection_changed`로 닫는다(Zabbix를 바꾸면 eventid가 겹쳐 장애가 섞이던 것, 준하 님 #214 리뷰).
- 이유: 한 설치를 여러 고객사(캣북스·누비투어·스터디온)가 쓰는데 018은 Zabbix 연결이 한 벌이라, 2026-11-26 실서버에서 누비투어 인프라 화면에 캣북스 장애가 보였고 누비투어가 Zabbix를 넣으면 캣북스 것을 덮게 됐다. 회사 개념은 AXcellent 쪽에 이미 있다(세션 회사·회사 연결 설정).
- 대안(기각): ① 회사마다 DejaFix를 따로 띄우기(018 대안 ②) — 서버 담당이 회사마다 손으로 띄워야 하고 AXcellent의 다른 AI와 구조가 다르다 ② 같이 설치된 DejaFix를 캣북스 전용으로 두기 — 다른 회사는 장애 대응을 못 쓴다(AXcellent 프록시는 이 결정이 구현되기 전까지만 이렇게 막는다, Axcellent-bs #1884)
- 결정자·일시 / 근거: 노예진 2026-11-26 / 결정 018, `contracts/api.md` 1장 "회사", `contracts/db-schema.sql` 019 이관

## 구현 순서 (계약 PR → 구현 PR, 파트별)
1. 계약(이 PR): api.md 1장 "회사"·#28·#29, agent-api.md 0장, mcp-tools.md 1장, db-schema.sql 회사 칸·019 이관
2. libs(`zabbix_ro` 연결 파일을 회사별로) — Backend 담당
3. backend(머리 읽기·조회 거르기·#28·#29 회사별·메일 회사별) — Backend 담당
4. scheduler(Zabbix 연결이 있는 회사마다 폴링, `company_id` 써 넣기, 019 이관 실행) — DB·메일 담당
5. agent·mcp-zabbix·mcp-kb(회사마다 MCP 세션, 지식 검색 회사별) — 팀장·Zabbix·MCP 담당
