# libs/zabbix_ro

Backend·mcp-zabbix·Scheduler가 함께 쓰는 읽기 전용 Zabbix 클라이언트 (uv workspace 멤버)

- 허용 메서드(기획서 6-2) 밖 호출은 네트워크 요청 **전에** 예외 (SAFE-02)
- 인증은 `Authorization: Bearer <ZABBIX_API_TOKEN>`, `user.login` 미사용
- `ZABBIX_MOCK=true`면 Zabbix 7.0 형식 fixture 반환
