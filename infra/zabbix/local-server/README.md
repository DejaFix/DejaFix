# 로컬 개발용 Zabbix 서버 (Docker)

Zabbix 7.0 LTS(7.0.31) 서버·웹 + PostgreSQL 16. Windows에서는 Zabbix 서버가 네이티브로 안 되므로 Docker Desktop(WSL2 백엔드)으로 띄운다.
**개발·검증용**이다. 운영 Zabbix(팀 Ubuntu VM)와 앱 compose(`infra/docker-compose.yml`)와는 별개이고, 여기 PostgreSQL은 Zabbix 서버 전용 DB다(앱 DB 아님).
포트는 모두 `127.0.0.1`에만 열린다(LAN 노출 없음). 팀 앱·팀 Zabbix VM 포트와 겹치지 않게 18xxx를 쓴다.

| 서비스 | 이미지 | 호스트 포트 (기본값, `.env`로 변경) |
|---|---|---|
| zabbix-web | `zabbix/zabbix-web-nginx-pgsql:alpine-7.0.31` | `127.0.0.1:18080` (웹 UI, API) — `ZBX_WEB_PORT` |
| zabbix-server | `zabbix/zabbix-server-pgsql:alpine-7.0.31` | `127.0.0.1:18051` (trapper) — `ZBX_TRAPPER_PORT` |
| postgres-server | `postgres:16-alpine` | 없음 (내부 네트워크만) |

DB 데이터는 named volume `dejafix-zabbix_zbx_pgdata`에 남는다.

## 실행 (PowerShell, 이 폴더에서)

```powershell
docker info                         # Docker Desktop 엔진이 떠 있는지 먼저 확인
Copy-Item .env.example .env         # .env가 없을 때만. 그다음 POSTGRES_PASSWORD를 바꾼다
docker compose up -d
docker compose ps                   # 세 컨테이너가 running(postgres는 healthy)인지 확인
docker compose logs -f zabbix-server
```

처음 한 번은 저장소 루트에서 `python infra\zabbix\local-server\setup_local_server.py --host-name $env:COMPUTERNAME --secrets $HOME\host-setup\zabbix-secrets.json`
으로 내 PC를 호스트로 등록하고 읽기 전용 토큰을 만든다(이 스크립트는 쓰기 작업이라 **운영 Zabbix에는 실행하지 않는다**).

## 중지

```powershell
docker compose stop        # 멈춤 (컨테이너 유지)
docker compose down        # 컨테이너 삭제, DB 볼륨은 유지
docker compose down -v     # DB 볼륨까지 삭제 (모든 Zabbix 데이터 사라짐, 주의)
```

## 접속

- 웹: http://127.0.0.1:18080 — 초기 계정 `Admin` (초기 비밀번호는 Zabbix 공식 문서 참고. `setup_local_server.py`가 마지막에 바꾸고 `--secrets` 파일에만 저장)
- API: `http://127.0.0.1:18080/api_jsonrpc.php`

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:18080/api_jsonrpc.php -Method Post -ContentType 'application/json-rpc' `
  -Body '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}'
```

## 메모

- 버전 규칙: 에이전트가 서버보다 높으면 안 된다. 서버 태그(7.0.31)를 에이전트보다 낮추지 않는다.
- 이 PC의 에이전트 액티브 체크는 `ServerActive=127.0.0.1:18051`로 보낸다. 패시브 체크(서버 → 에이전트 10050)는 컨테이너에서 `host.docker.internal`로 접속하는 방식이 될 것이다 (추정, 미검증).
- 2026-10-15 이전에는 8080·10051을 썼다. 앱 공개 포트(8080)·팀 Zabbix VM 포워딩(10051)과 겹쳐 18080·18051로 옮겼다.
