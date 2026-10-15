# infra/zabbix — Zabbix 영역

운영 Zabbix(팀 서버)는 플랫폼 밖의 외부 서비스다. 플랫폼은 운영 Zabbix를 **조회만** 한다(멘토 구성도 설계 원칙).
이 폴더에는 그 조회를 개발·검증하기 위한 로컬 환경과 도구, 감시 대상 PC에 에이전트를 까는 방법을 둔다.

| 경로 | 내용 | 비고 |
|---|---|---|
| `local-server/` | 로컬 개발용 Zabbix 7.0.31 서버(Docker compose) + 초기 설정 `setup_local_server.py` | 127.0.0.1 전용. `setup_local_server.py`는 **쓰기 작업**(호스트·역할·토큰 생성)이라 운영 Zabbix에는 실행하지 않는다 |
| `tools/` | 점검·검증 도구 | 아래 표 |
| (예정) 웹훅 | 운영 Zabbix 알람 전달 설정 | 웹훅으로 받을지 주기 조회할지 팀 결정 전 |

## tools/

| 파일 | 하는 일 |
|---|---|
| `check_zabbix.ps1` | 로컬 서버 컨테이너, 설치된 에이전트(버전 ≤ 대상 서버, 서버 주소 형식, 마지막 연결 오류), API, 핵심 지표 최신값을 `[OK]/[FAIL]`로 출력 |
| `start_dashboard.ps1` | 로컬 서버 → 수집용 포터블 Agent 2 → 대시보드(127.0.0.1:8090)를 한 번에 켬 |
| `dashboard/` | 핵심 지표(CPU/MEM/DISK/NET) 대시보드 **시제품**. 실제 화면은 `frontend/`, 실제 API는 `backend/`에서 만든다 |
| `core_metrics.py` | API로 핵심 지표 최신값 출력 |
| `zabbix_api_probe.py` | 조회 API 7개(host/item/history/trend/problem/event/trigger.get)를 읽기 전용으로 호출해 응답 저장 |
| `verify_agent_items.py` | 에이전트에 패시브 질의를 보내 Item key별 결과 기록 |
| `mock_active_server.py` | 액티브 체크 검증용 모의 수신기(Zabbix 서버 아님) |
| `active_check_probe.py` | 서버가 내 호스트를 아는지 확인. 에이전트와 같은 "active checks" 요청을 보내고 응답(`success`/`host [...] not found`)을 출력 — `python active_check_probe.py <서버 주소> <에이전트 Hostname>` |

실행: `powershell -ExecutionPolicy Bypass -File infra\zabbix\tools\check_zabbix.ps1`

## 감시 대상 Windows PC에 에이전트 설치 (팀 서버용)

- 버전: 에이전트는 서버보다 높으면 안 된다. 팀 서버가 7.0.31이므로 **7.0.31**을 쓴다.
- 설치 파일: `https://cdn.zabbix.com/zabbix/binaries/stable/7.0/7.0.31/zabbix_agent-7.0.31-windows-amd64-openssl.msi`
  SHA256 `0c382d6029017a570a5d99a0e6e0dde964fc3c468e80baa1f53bd673531db6f8`(https://www.zabbix.com/download_agents 페이지의 값), 서명 `CN=Zabbix SIA`.
- 관리자 PowerShell:

```powershell
msiexec /i zabbix_agent-7.0.31-windows-amd64-openssl.msi /qn /norestart `
  SERVER=<팀 서버 주소> SERVERACTIVE=<팀 서버 주소>:10051 HOSTNAME=<팀 서버에 등록한 호스트 이름> SKIP=fw
```

- `HOSTNAME`은 팀 서버에 등록한 이름과 대소문자까지 같아야 한다. 템플릿은 `Windows by Zabbix agent active`.
- `SKIP=fw`: 방화벽 예외를 만들지 않는다(액티브 방식은 PC → 서버 10051 연결만 쓴다).
- 이미 더 높은 버전이 깔려 있으면 덮어 설치가 안 된다. 먼저 제거하고 설치한다(제거하면 conf도 지워지니 백업).
- 확인: `C:\Program Files\Zabbix Agent\zabbix_agentd.log`에 `host [...] not found`가 나오면 서버 쪽 호스트 등록이 필요하다.

## 비밀 값

서버 주소, Admin 비밀번호, API 토큰, `.env`는 저장소에 쓰지 않는다. 로컬 값은 각자 PC의 저장소 밖 파일에 둔다.

관련 문서: `docs/zabbix/README.md`
