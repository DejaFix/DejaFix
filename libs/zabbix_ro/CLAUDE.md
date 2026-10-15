# libs/zabbix_ro

## 역할
- [필수] 허용 목록 강제 클라이언트: `apiinfo.version, problem.get, event.get, trigger.get, host.get, hostgroup.get, hostinterface.get, item.get, history.get, trend.get, maintenance.get, action.get, alert.get` 외 메서드는 요청 전 `MethodNotAllowed` (FR-LIB-001)
- [필수] Bearer 토큰 인증, `ZABBIX_VERIFY_TLS` 반영 (FR-LIB-002)
- [필수] `ZABBIX_MOCK=true` fixture(`problem.get`, `host.get`, `item.get`, `history.get` 등) (FR-LIB-003)

## 하지 않는 것
- 쓰기 메서드(`*.create/update/delete`), `user.login`
- IT 전용 아이템 키 하드코딩 (키는 `packs/<domain>/metrics.yaml`)

## 테스트
- `uv run pytest` — SAFE-02: `host.update`, `item.create`, `user.login`, `problem.delete` → 요청 없이 예외 (머지 조건)
