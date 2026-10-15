# zabbix — Zabbix 조사·설정 기록 (서버 Zabbix·MCP 담당 · 에이전트·템플릿 팀장)

여기에 남겨야 닫히는 항목(요구사항 수용 기준이 "`docs/zabbix/`에 기록"인 것들).

| 기록 | 내용 | 근거 | 담당 |
|---|---|---|---|
| `version.md` | VM OS·Zabbix 버전·설치 방식(apt / VM 내 Docker), `apiinfo.version` 응답 캡처 | FR-ZBX-001, G1 | Zabbix·MCP 담당 |
| `readonly-account.md` | `dejafix-readonly` 사용자·그룹·권한, API 토큰 발급 절차(값 제외), **`host.update` 호출 시 권한 오류 캡처** | FR-ZBX-004, NFR-SAFE-001 | Zabbix·MCP 담당 |
| `access.md` | 접속 방식 `(TODO: 추후결정 — 후보: 포트 포워딩 8081·10051 / 브리지 IP)`, `ZABBIX_URL` 형식, 방화벽 설정, 아침 점검 절차 결과 | FR-ZBX-006, G7 | Zabbix·MCP 담당 |
| `agent-items.md` | 데모 PC agent 2 설치 결과, 템플릿 이름, **실제 아이템 키**(cpu·mem·disk·net, 인터페이스 이름 포함), 스왑 free 불일치 메모 | FR-ZBX-002·007, G2·G18 | 팀장 |
| `demo-trigger.md` | 데모 템플릿 복제본(CPU 아이템 30초), 트리거 `avg(/<호스트>/system.cpu.util,1m)>85` High, 1회 발동 확인 시각 | FR-ZBX-003, G6 | 팀장 |
| `api-list.md` | 노션 "자빅스 API 목록"(멘토 순서 ②)의 사본 또는 링크 — 수집 항목 CPU/MEM/DISK/Network, 사용 메서드 | FR-INF-014 | 팀장·Zabbix·MCP 담당 |
| `mcp-live-test.md` | 토큰 수령 후 MCP 5도구 실호출 결과(B3 DoD ③) | FR-MCP-002~006 | Zabbix·MCP 담당 |

- 토큰·비밀번호 **값은 어디에도 적지 않는다**(Slack 1:1 DM만, 11-4).
- 허용 메서드 13개(기획서 6-2): `apiinfo.version, problem.get, event.get, trigger.get, host.get, hostgroup.get, hostinterface.get, item.get, history.get, trend.get, maintenance.get, action.get, alert.get`. `user.login` 미사용.
