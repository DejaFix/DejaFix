# 읽기 전용 계정 `dejafix-readonly` (T56, FR-ZBX-004)

> 토큰 값은 이 문서에 적지 않는다(Slack 1:1 DM). 확인일: 2026-10-15, 팀 Zabbix 7.0.31 웹 화면과 실호출로 확인.
> 운영 Zabbix 쓰기(역할·사용자·토큰 생성)는 DejaFix 서비스가 아니라 **사람이 웹에서** 했다.

## 구성
| 항목 | 설정 |
|---|---|
| 사용자 역할 `dejafix-readonly` | 유형 **User**, Access to API **Enabled**, **Allow list**: `action.get`, `alert.get`, `event.get`, `history.get`, `host.get`, `hostgroup.get`, `hostinterface.get`, `item.get`, `maintenance.get`, `problem.get`, `trend.get`, `trigger.get` (12개) |
| `apiinfo.version` | 허용 목록에 넣지 않는다(인증 없이 누구나 호출 가능하고 역할 선택지에도 없음). `libs/zabbix_ro`도 이 메서드는 토큰 없이 보낸다 |
| 사용자 그룹 `dejafix-readonly` | Frontend access **Disabled**, Debug mode Disabled, Host permissions: `Windows`·`Zabbix servers` 그룹에 **Read** |
| 사용자 `dejafix-readonly` | 위 그룹·역할, Frontend access Disabled, **API access Enabled** |
| API 토큰 | 사용자 `dejafix-readonly`, 만료일 설정(날짜는 기록하지 않음). 값은 생성 직후 한 번만 보이므로 DM으로만 전달 |

허용 메서드 13개는 기획서 6-2 기준이고 그중 `apiinfo.version`을 뺀 12개를 역할에 넣었다. `user.login`은 쓰지 않는다.

## 보완 여지 (필수 아님)
역할의 **Access to actions**(문제 확인·종료, 스크립트 실행, API 토큰 관리 등)와 "Default access to new actions·modules"가 기본값 그대로 켜져 있다. API 허용 목록이 실제 호출을 막고 Frontend access가 Disabled라 영향은 없지만, 풀어 두면 더 안전하다.

## 확인한 것
- `dejafix-readonly` 토큰으로 `problem.get`·`event.get`·`trigger.get`·`host.get`·`item.get`·`history.get` 성공 → `mcp-live-test.md`
- 로컬 개발 서버에서는 허용 목록 밖 `user.get`이 차단되는 것을 확인했다(`verification/api-probe-2026-10-14/`).

## 아직 없는 것
- **`host.update` 호출 시 권한 오류 캡처**(FR-ZBX-004, NFR-SAFE-001 증빙). `libs/zabbix_ro`가 쓰기 메서드를 요청 전에 막기 때문에 라이브러리로는 못 보이고, 토큰과 `curl`/`Invoke-RestMethod`로 직접 호출해야 한다. 캡처(토큰·주소 가림)를 이 문서에 추가한다.
