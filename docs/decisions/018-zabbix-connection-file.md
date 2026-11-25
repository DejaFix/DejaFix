# 018 화면에서 Zabbix 연결 — 연결 파일에 토큰을 둔다 (SAFE-13 예외)
- 결정: 고객사가 AXcellent 화면에서 자기 Zabbix 주소·읽기 전용 API 토큰을 넣으면 Backend 관리자 API(`PUT /api/settings/zabbix`, 계약 #29)가 `ZABBIX_CONNECTION_FILE`(JSON, 0600)에 저장하고, `libs/zabbix_ro`(`from_env`·`live_from_env`)가 `.env`보다 이 파일을 먼저 쓴다. Backend·Scheduler·mcp-zabbix는 재시작 없이 새 연결을 따른다. 파일이 없으면 지금처럼 `.env`다.
- 이유: DejaFix는 AXcellent와 같이 설치되고, 고객사는 자기 Zabbix만 안다. 서버 담당이 `.env`를 고쳐 주기를 기다리지 않고 고객사가 직접 연결해야 한다. 토큰은 "읽기 전용" 계정 것만 받고, 저장 전에 허용 목록 안의 조회(`apiinfo.version`·`host.get`)로 확인하며, 응답·로그·오류 문장에 넣지 않는다. 파일은 `/data` 볼륨(compose 밖에서 접근 불가)에 0600으로 둔다.
- SAFE-13 예외: "키는 `.env`에만"의 예외로, Zabbix 읽기 토큰 하나만 연결 파일에 둘 수 있다. 다른 비밀값(LLM·SMTP·JWT)은 그대로 `.env`만.
- 대안(기각): ① `.env`를 화면에서 고치기 — 다른 비밀값까지 같은 파일이라 위험이 크다 ② 회사마다 DejaFix를 따로 띄우기 — 서버 담당이 매번 손으로 해야 한다 ③ DejaFix 하나가 여러 회사 Zabbix를 같이 보기 — 전 구간에 회사 개념이 필요해 범위가 크다([이후])
