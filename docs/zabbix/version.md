# 팀 Zabbix 서버 버전·설치 방식 (T10, FR-ZBX-001)

> 서버 주소·토큰 값은 이 문서에 적지 않는다(`<서버 주소>`로 표기). 접속 방법은 `access.md`.
> 확인일: 2026-10-16 (Zabbix·MCP 담당). 서버 셸 출력(`systemctl status`·`journalctl`·`apt history`)과 `apiinfo.version` 응답에서 옮겼다. 직접 못 본 칸은 `확인 못 함`으로 둔다.

## 확정 값
| 항목 | 값 | 근거 |
|---|---|---|
| Zabbix 서버·프론트 버전 | **7.0.31** | `apiinfo.version` 응답 `"result":"7.0.31"` (2026-10-16 확인) |
| OS | Ubuntu 24.04 계열(패키지 접미사 `ubuntu…24.04`), 호스트 이름 `himedia-2` | `apt history`의 패키지 버전. 정확한 `lsb_release` 출력은 확인 못 함 |
| 설치 방식 | **apt 패키지(VM에 직접 설치).** Docker 아님 | 서비스 유닛이 `/usr/lib/systemd/system/zabbix-server.service`, `zabbix-server`·`mariadb`가 systemd 서비스로 동작 |
| 데이터베이스 | MariaDB 10.11.14 (PostgreSQL 없음) | `systemctl status mariadb`, `Unit postgresql.service could not be found` |
| 웹 서버 | Apache 2.4.x (`apache2`, 패키지 2.4.58-1ubuntu8.x) | `apt history` |
| 서버 자동 업그레이드 | 켜져 있음(`unattended-upgrade`) | `apt history` 2026-10-16 12:39 |
| 에이전트(감시 PC) | Zabbix Agent 7.4.15(데모 PC `Heon-PC`) — 서버(7.0)보다 높은 버전이나 수집 정상 | 에이전트 로그 |
| 웹 경로·포트 | `http://<서버 주소>/zabbix`, **80번**. 트래퍼 10051 | `access.md` |

## `apiinfo.version` 응답 캡처 (토큰 불필요)
```json
{"jsonrpc":"2.0","result":"7.0.31","id":1}
```
요청: `POST http://<서버 주소>/zabbix/api_jsonrpc.php`, 본문 `{"jsonrpc":"2.0","method":"apiinfo.version","params":[],"id":1}`. 이 호출은 인증 없이 되고, 아침 점검과 `/api/health`의 Zabbix 판정(T31)에도 같은 방식이 쓰인다.

## 알아둘 점 (운영 기록)
- **2026-10-16 06:05 KST에 MariaDB와 `zabbix-server`가 같은 초에 정지**했고, 약 6시간 뒤(오전 12시대) 수동으로 복구했다. 웹은 `Database error: No such file or directory`(DB 소켓 파일 없음), API는 `Internal error`를 냈다.
  - MariaDB 로그는 `Normal shutdown (initiated by: unknown)`이고 크래시가 아니었다. 디스크는 14% 사용으로 여유가 있었고, 재부팅은 없었다(`uptime -s` 2026-10-14 16:19).
  - **원인은 확정하지 못했다.** 새벽 `unattended-upgrade`가 서비스를 멈추고 다시 올리지 못했을 가능성이 가장 높지만 06:0x 시각의 `apt history`는 확인하지 못했다.
- **재발 방지(결정 필요, 서버 설정 변경이라 서버 관리자 몫):** 데모 전까지 `apt-daily-upgrade.timer`를 끄거나 `50unattended-upgrades`의 `Package-Blacklist`에 `mariadb-*`·`zabbix-*`를 넣는다. 데모 후 되돌린다.
- 복구 순서: `zabbix-server`가 `deactivating`에 걸려 있으면 `systemctl kill -s KILL zabbix-server` → `systemctl start mariadb` → `systemctl start zabbix-server`.

## 아직 확인 못 한 것
- `lsb_release -a`(정확한 Ubuntu 버전), `apt list --installed | grep -E "zabbix|mariadb"`(설치 패키지 버전 전체)는 서버 셸이 필요해 이 문서에 넣지 못했다. 서버 관리자가 출력을 붙이면 위 표를 보완한다.
