# libs/zabbix_ro

Backend·mcp-zabbix·Scheduler가 함께 쓰는 읽기 전용 Zabbix 클라이언트 (uv workspace 멤버)

- 허용 메서드(기획서 6-2) 밖 호출은 네트워크 요청 **전에** 예외 (SAFE-02)
- 인증은 `Authorization: Bearer <ZABBIX_API_TOKEN>`, `user.login` 미사용
- `ZABBIX_MOCK=true`면 Zabbix 7.0 형식 fixture 반환

## 사용법

```python
import zabbix_ro

client = zabbix_ro.from_env()   # 환경 변수에서 만든다
problems = client.call("problem.get", {"output": "extend", "recent": True})  # JSON-RPC result
```

| 환경 변수 | 뜻 |
|---|---|
| `ZABBIX_URL` | `.../api_jsonrpc.php` 주소. 실서버 모드에서 필수 |
| `ZABBIX_API_TOKEN` | 읽기 전용 계정의 API 토큰. 실서버 모드에서 필수(값은 `.env`에만) |
| `ZABBIX_VERIFY_TLS` | `false`면 TLS 인증서 검사를 끈다. 기본 `true` |
| `ZABBIX_MOCK` | `true`면 네트워크 없이 fixture 를 돌려준다. URL·토큰이 없어도 된다 |

## 허용 메서드 (13개)

`apiinfo.version`, `problem.get`, `event.get`, `trigger.get`, `host.get`, `hostgroup.get`, `hostinterface.get`, `item.get`, `history.get`, `trend.get`, `maintenance.get`, `action.get`, `alert.get`

`*.create`·`*.update`·`*.delete`·`user.login` 등 그 밖의 메서드는 요청을 보내기 전에 `MethodNotAllowed`.

## 예외

| 예외 | 언제 |
|---|---|
| `zabbix_ro.MethodNotAllowed` | 허용 목록 밖 메서드 (요청 전) |
| `zabbix_ro.ZabbixError` | URL·토큰 누락, 연결 실패, 타임아웃, HTTP 오류, JSON-RPC `error` 응답 (`.code`·`.data`) |
| `zabbix_ro.ZabbixRoError` | 위 둘의 부모. 한 번에 잡을 때 |

## 목 모드 (fixture)

`zabbix_ro/fixtures/`는 `docs/zabbix/verification/api-probe-2026-10-14/`의 실서버(7.0.31) 응답을 복사한 것이다.
- `trigger.get`의 `hosts`에는 `host.get`의 `name`을 보강했다(Scheduler가 `selectHosts`로 `name`을 요청).
- `history.get`은 `params.history`(0~3) 값에 맞는 파일을 쓴다.
- `eventids`·`triggerids`·`hostids`·`itemids`·`objectids`·`limit` 파라미터로 간단히 거른다. 그 밖의 필터·정렬은 하지 않는다.
- fixture 가 없는 허용 메서드(`hostgroup.get` 등)는 빈 목록.

## 테스트

`uv run pytest libs/zabbix_ro` — SAFE-02(쓰기 메서드는 요청 없이 거부)는 `safety_regression` 마커.
