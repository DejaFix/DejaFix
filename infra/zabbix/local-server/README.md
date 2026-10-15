# Zabbix 서버 (Docker)

Zabbix 7.0 LTS(7.0.31) 서버·웹 + PostgreSQL 16. Windows에서는 Zabbix 서버가 네이티브로 안 되므로 Docker Desktop(WSL2 백엔드)으로 띄운다.
포트는 모두 `127.0.0.1`에만 열린다(LAN 노출 없음).

| 서비스 | 이미지 | 호스트 포트 |
|---|---|---|
| zabbix-web | `zabbix/zabbix-web-nginx-pgsql:alpine-7.0.31` | `127.0.0.1:8080` (웹 UI, API) |
| zabbix-server | `zabbix/zabbix-server-pgsql:alpine-7.0.31` | `127.0.0.1:10051` (trapper) |
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

## 중지

```powershell
docker compose stop        # 멈춤 (컨테이너 유지)
docker compose down        # 컨테이너 삭제, DB 볼륨은 유지
docker compose down -v     # DB 볼륨까지 삭제 (모든 Zabbix 데이터 사라짐, 주의)
```

## 접속

- 웹: http://127.0.0.1:8080 — 초기 계정 `Admin` (초기 비밀번호는 Zabbix 공식 문서 참고, 첫 로그인 직후 바꾼다)
- API: `http://127.0.0.1:8080/api_jsonrpc.php`

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8080/api_jsonrpc.php -Method Post -ContentType 'application/json-rpc' `
  -Body '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}'
```

## 메모

- 버전 규칙: 에이전트가 서버보다 높으면 안 된다. 이 PC의 Zabbix Agent 2는 7.0.31이므로 서버 태그를 내리지 않는다.
- 이 PC의 에이전트 active 체크는 `127.0.0.1:10051`로 보낼 수 있다. passive 체크(서버 → 에이전트 10050)는 컨테이너에서 `host.docker.internal`로 접속하는 방식이 될 것이다 (추정, 미검증).
