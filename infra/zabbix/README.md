# infra/zabbix — Zabbix 영역

운영 Zabbix(팀 서버)는 플랫폼 밖의 외부 서비스다. 플랫폼은 운영 Zabbix를 **조회만** 한다(멘토 구성도 설계 원칙).
이 폴더에는 그 조회를 개발·검증하기 위한 로컬 환경과 도구, 감시 대상 PC에 에이전트를 까는 방법을 둔다.

| 경로 | 내용 | 비고 |
|---|---|---|
| `local-server/` | 로컬 개발용 Zabbix 7.0.31 서버(Docker compose) + 초기 설정 `setup_local_server.py` | 127.0.0.1 전용. `setup_local_server.py`는 **쓰기 작업**(호스트·역할·토큰 생성)이라 운영 Zabbix에는 실행하지 않는다 |
| `tools/` | 점검·진단 도구, 핵심 지표 대시보드 시제품 | 아래 표 |
| (예정) 웹훅 | 운영 Zabbix 알람 전달 설정 | 웹훅으로 받을지 주기 조회할지 팀 결정 전 |

## 포트 (모두 127.0.0.1에만 열림)

팀 앱(8080 공개, 8000 backend, 8100 agent, 5173 vite)과 팀 Zabbix VM 포워딩(8081 웹, 10051 트래퍼)과 겹치지 않게 **18xxx**를 쓴다.

| 포트 | 무엇 | 바꾸는 곳 |
|---|---|---|
| 18090 | 핵심 지표 대시보드 | `start_dashboard.ps1 -DashboardPort`, `server.py --port` |
| 18080 | 로컬 Zabbix 웹·API | `local-server/.env`의 `ZBX_WEB_PORT` + 스크립트 `-WebPort` |
| 18051 | 로컬 Zabbix 트래퍼(에이전트 액티브 체크) | `local-server/.env`의 `ZBX_TRAPPER_PORT` + 에이전트 conf `ServerActive` |
| 10060 | 로컬 방식 수집용 Agent 2(패시브 수신) | 에이전트 conf `ListenPort` |

## 핵심 지표 대시보드 보기

CPU / MEM / DISK / Network 4칸 화면이다. 현재 값, 최근 1시간 그래프, 템플릿 기준선, 열린 장애를 30초마다 갱신한다.
Zabbix API를 **읽기 전용 토큰으로 조회만** 하고, 토큰은 대시보드 서버(내 PC의 python)에만 있고 브라우저로 보내지 않는다.
대시보드는 **각자 자기 PC에서 띄워서 자기 브라우저로 본다.** 다른 PC에서 접속하는 방식(LAN 공개)은 막아 두었다(127.0.0.1 전용, 방화벽 개방 불필요).

### 방법 A. 팀 Zabbix 서버를 바로 보기 (팀원 권장)

준비물
- Python 3.12 (표준 라이브러리만 씀, `pip install` 필요 없음)
- 팀 Zabbix API 주소 — 팀 `.env`의 `ZABBIX_URL` 값(예: `http://<팀 서버 주소>/zabbix/api_jsonrpc.php`)
- 읽기 전용 API 토큰 — 팀 서버 담당에게 Slack DM으로 받는다. 파일·커밋·채팅에 붙여넣지 않는다
- 보고 싶은 호스트 이름 — 팀 Zabbix에 등록된 **Host name**(대소문자 일치). 생략하면 내 PC 이름(`$env:COMPUTERNAME`)

실행 (PowerShell, 저장소 루트)

```powershell
git fetch origin
git switch feat/infra-zabbix-agent            # dev에 머지된 뒤에는 dev
$env:ZABBIX_API_TOKEN = '<받은 토큰>'          # 이 터미널에만 남는다
powershell -ExecutionPolicy Bypass -File infra\zabbix\tools\start_dashboard.ps1 `
  -Remote 'http://<팀 서버 주소>/zabbix/api_jsonrpc.php' -HostName '<Zabbix 호스트 이름>'
```

브라우저가 http://127.0.0.1:18090 으로 열린다. PowerShell 스크립트를 못 쓰면 같은 일을 python으로 직접 한다.

```powershell
python infra\zabbix\tools\dashboard\server.py --url 'http://<팀 서버 주소>/zabbix/api_jsonrpc.php' --host '<Zabbix 호스트 이름>'
# 그다음 브라우저에서 http://127.0.0.1:18090
```

### 방법 B. 내 PC에 로컬 Zabbix까지 띄워서 보기 (Zabbix 개발·검증용)

팀 서버 없이 내 PC 하나로 수집부터 화면까지 확인할 때 쓴다. 준비가 많다.

1. Docker Desktop 실행 → `local-server/README.md`대로 `.env`를 만들고 `docker compose up -d`
2. `python infra\zabbix\local-server\setup_local_server.py --host-name $env:COMPUTERNAME --secrets $HOME\host-setup\zabbix-secrets.json`
   (내 PC를 호스트로 등록, 읽기 전용 토큰 생성 → 토큰은 저장소 밖 `--secrets` 파일에만 저장)
3. Zabbix Agent 2 7.0.31 압축본을 `$HOME\zabbix-agent2\portable\`에 풀고, `$HOME\zabbix-agent2\local-dashboard\zabbix_agent2.conf`를 만든다:
   `Server=127.0.0.1`, `ListenIP=127.0.0.1`, `ListenPort=10060`, `ServerActive=127.0.0.1:18051`, `Hostname=<내 PC 이름>`
   (다른 위치면 `start_dashboard.ps1 -AgentExe ... -AgentConf ...`)
4. `powershell -ExecutionPolicy Bypass -File infra\zabbix\tools\start_dashboard.ps1`
   → 로컬 서버 → 수집용 에이전트 → 대시보드(http://127.0.0.1:18090)를 순서대로 켠다

### 화면이 비어 있을 때

| 증상 | 확인 |
|---|---|
| "Zabbix API에 연결하지 못했습니다" | 주소(`/zabbix` 경로 유무), 토큰, 네트워크. `Invoke-RestMethod`로 `apiinfo.version`이 오는지 |
| 카드가 "값 없음" | 그 호스트에 데이터가 안 들어오는 중. 호스트 이름이 정확한지, 에이전트가 붙었는지(`tools\active_check_probe.py <서버 주소> <호스트 이름>`이 `success`인지) |
| 디스크 지연·네트워크만 "값 없음" | 템플릿 자동 탐색(최대 1시간) 전. 기다리면 생긴다 |

## tools/

| 파일 | 하는 일 |
|---|---|
| `start_dashboard.ps1` | 대시보드 실행. 기본은 로컬 방식, `-Remote <API URL>`이면 팀 서버를 바로 조회 |
| `dashboard/` | 핵심 지표(CPU/MEM/DISK/NET) 대시보드 **시제품**(`server.py` + `index.html`). 실제 화면은 `frontend/`, 실제 API는 `backend/`에서 만든다 |
| `check_zabbix.ps1` | 로컬 서버 컨테이너, 설치된 에이전트(버전 ≤ 대상 서버, 서버 주소 형식, 마지막 연결 오류), API, 핵심 지표 최신값을 `[OK]/[FAIL]`로 출력 |
| `active_check_probe.py` | 서버가 내 호스트를 아는지 확인. 에이전트와 같은 "active checks" 요청을 보내고 응답(`success`/`host [...] not found`)을 출력 — `python active_check_probe.py <서버 주소> <에이전트 Hostname>` |
| `core_metrics.py` | API로 핵심 지표 최신값 출력 |
| `zabbix_api_probe.py` | 조회 API 7개(host/item/history/trend/problem/event/trigger.get)를 읽기 전용으로 호출해 응답 저장 |
| `verify_agent_items.py` | 에이전트에 패시브 질의를 보내 Item key별 결과 기록 |
| `mock_active_server.py` | 액티브 체크 검증용 모의 수신기(Zabbix 서버 아님) |

토큰은 모든 도구가 환경 변수 `ZABBIX_API_TOKEN`을 먼저 쓰고, 없으면 `--secrets <json>`(`{"api_token": "..."}`)을 읽는다. API 주소는 `--url`, 없으면 `ZABBIX_URL`, 없으면 로컬 서버(18080).

## 감시 대상 Windows PC에 에이전트 설치 (팀 서버용)

- 버전: 에이전트는 서버보다 높으면 안 된다(공식 호환 규칙). 팀 서버가 7.0.31이므로 **7.0.31**을 쓴다.
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

관련 문서: `docs/zabbix/README.md`, `docs/zabbix/core-metrics.md`

참고: `docs/zabbix/windows-agent-api.md`의 검증 기록(2026-10-14)에 나오는 `127.0.0.1:8080`·`127.0.0.1:10051`은 포트를 옮기기 전 값이다. 지금 로컬 서버는 18080·18051이다.
