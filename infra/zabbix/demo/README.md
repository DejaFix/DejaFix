# infra/zabbix/demo — 데모 템플릿·트리거 (T59, FR-ZBX-003·NFR-PERF-006)

데모 장면 D-MAIN(`docs/demo/README.md`)에서 `infra/scripts/inject-cpu.ps1`로 CPU를 올렸을 때 **90초 안에 High 장애**가 열리게 하는 템플릿이다.

## 파일
| 파일 | 내용 |
|---|---|
| `dejafix-demo-windows-active.yaml` | 템플릿 **`DejaFix Demo Windows by Zabbix agent active`** (Zabbix 7.0 내보내기 형식) |

원본 `Windows by Zabbix agent active`(7.0.31 기본 템플릿)를 내보내 아래 두 가지만 바꿨다. 나머지 항목·LLD·트리거·그래프는 원본과 같고, uuid는 원본과 겹치지 않게 새로 만들었다.
1. `system.cpu.util` 수집 주기 **1m → 30s**
2. 트리거 추가: **`DejaFix demo: CPU 1분 평균 85% 초과`** — `avg(/DejaFix Demo Windows by Zabbix agent active/system.cpu.util,1m)>85`, 심각도 **High**, 태그 `scope=performance`·`dejafix=demo`. 평균이 85% 아래로 내려가면 자동 해소

원본 트리거 `Windows: High CPU utilization`(`min(...,5m)>90`, Warning)은 5분을 기다려야 해서 데모 시간 예산(트리거 60초, `docs/demo/README.md`)에 맞지 않는다.

- 트리거 식은 템플릿 이름을 참조하므로 **호스트 이름과 무관**하다. 데모 호스트 이름은 `(TODO: 추후결정 — 후보: LAB-PC-DEMO)`(결정 008)이며 이 파일에 적지 않는다.
- 시간 예산(추정): 수집 30초 간격 + 1분 평균이 85%를 넘는 데 약 60초 → 주입 후 약 60~90초.

## 검증한 것 (2026-10-15, 로컬 개발 서버 7.0.31)
- `configuration.import` 성공, 템플릿 생성 확인: `system.cpu.util` delay `30s`, 데모 트리거 priority `4`(High), 식 위와 동일
- 로컬 서버에서는 **호스트에 연결하지 않았다**(기존 설정을 바꾸지 않기 위해). 그래서 **실제 발동(주입 → Problem)은 아직 확인하지 않았다** → 아래 4단계로 팀 서버에서 확인

## 팀 서버에 적용 (Zabbix·MCP 담당, 관리자 권한 필요)
운영 Zabbix 쓰기 작업이므로 **DejaFix 서비스(Backend·MCP·Scheduler)가 아니라 사람이 웹 화면에서** 한다(플랫폼은 조회만).
1. **가져오기**: Data collection → Templates → Import → 이 YAML 선택 → 기본 규칙(Create new) 그대로 Import
2. **데모 호스트에 연결**: Data collection → Hosts → 데모 호스트 → Templates에서
   - 원본 `Windows by Zabbix agent active`는 **Unlink and clear** (Unlink만 하면 원본 항목이 호스트에 남아 같은 키가 충돌해 연결이 실패한다. 기존 이력은 지워진다)
   - `DejaFix Demo Windows by Zabbix agent active` 추가 → Update
   - 데모 호스트 외 다른 호스트는 원본 템플릿을 그대로 둔다
3. **수집 확인**: Monitoring → Latest data에서 `CPU utilization` 값이 30초마다 갱신되는지
4. **발동 확인**(낮에만, 야간 금지): 데모 PC에서 `powershell -ExecutionPolicy Bypass -File infra\scripts\inject-cpu.ps1 -Minutes 3` → 90초 안에 Monitoring → Problems에 `DejaFix demo: CPU 1분 평균 85% 초과`(High) → `cleanup.ps1` 후 해소 확인. 걸린 시간은 `docs/demo/rehearsal-log.md`

## 다시 만들 때
로컬 개발 서버에서 원본 템플릿을 `configuration.export`(yaml)로 내보내고 위 두 가지만 바꾼 뒤 uuid를 새로 만든다. 템플릿 이름이 들어간 곳(트리거·그래프 식의 `/템플릿/`, 그래프 항목의 `host:`)을 모두 바꿔야 가져오기가 된다(바꾸지 않으면 `Item with ID ... is not available`).
