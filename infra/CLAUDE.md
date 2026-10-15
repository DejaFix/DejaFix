# infra — compose·Dockerfile·운영 스크립트·Zabbix 설정 기록

주담당: compose·Dockerfile 연동·인프라 담당(부 Backend 담당) / `scripts/` Zabbix·MCP 담당(부 팀장, 백업 스크립트는 DB·메일 담당) / `zabbix/` Zabbix·MCP 담당(서버)·팀장(에이전트·템플릿·트리거).
먼저 읽을 것: 루트 `CLAUDE.md` → `docs/mvp-checklist.md` "인프라·운영" → 기획서 3-3(compose)·11장(운영)·13-6(Windows 주의점).

## 역할 ([필수])
- **`infra/docker-compose.yml`**: 서비스 5개 `frontend, backend, agent, mcp-zabbix, scheduler`. 호스트 공개 포트는 **`8080:80`(frontend) 하나**, 나머지는 `expose`만. Python 4개 서비스는 **`build: { context: .., dockerfile: <svc>/Dockerfile }`**(루트 컨텍스트 — `libs/zabbix_ro`와 `packs/`가 이미지에 들어가야 함. `build: ../backend`식은 빌드가 깨진다). `env_file: ../.env`, named volume `dejafix-data:/data`(backend·agent·scheduler), `restart: unless-stopped`, 네트워크 `dejafix-net`. `mcp-aws`는 `profiles: ["aws"]` 주석만 (FR-INF-001, NFR-SAFE-014, NFR-SEC-002, NFR-AVAIL-001)
- **SQLite 볼륨**: 반드시 named volume(WSL2 ext4). Windows 폴더 바인드 마운트(`C:\...:/data`)는 WAL 잠금이 불안정해 금지. 파일을 볼 때는 `docker compose exec backend sqlite3 /data/shared.db` (NFR-PORT-002)
- **Dockerfile**: Python은 `uv`로 설치(`uv sync --frozen --package <svc>`), 서비스별 CMD. frontend는 Node 22로 빌드 → nginx 이미지(`frontend/nginx.conf`는 frontend 폴더 소유)
- **`scripts/`**(`scripts/README.md`): `inject-cpu.ps1`(기본·최대 10분, 코어 수만큼, 만료·Ctrl+C 시 종료), `cleanup.ps1`(주입 프로세스 종료·`%TEMP%\dejafix-fill\` 삭제), `backup-db.ps1`(SQLite 백업 API로 두 파일 → `backups/`, 최근 5개, 10/16 11:30 골든 백업) — 필수. `inject-disk.ps1`·`check-env.ps1`은 선택 (FR-INF-003·005·006)
- **`zabbix/`**: VM 설치 결과·버전·접속 방식 기록(`infra/zabbix/README.md`), 데모 템플릿·트리거 정의, 선택 `docker-compose.zabbix.yml`(VM에 못 붙는 팀원용 profile). 운영 Zabbix는 **우리 compose에 넣지 않는다**(외부 서비스, CON-009)
- 로컬 프로세스 대체 실행 절차(탈출 규칙 3): `uv run --package <svc> …` + `npm run preview`로 5개를 띄워 같은 흐름 — 루트 `README.md`에 기록 (FR-INF-009)

## 운영 규칙 (기획서 11장)
- 기동·재기동: `docker compose -f infra/docker-compose.yml --env-file .env up -d --build` / `ps` / `logs -f --tail=100 <svc>` / `restart <svc>`. **`.env`를 바꾸면 `restart`가 아니라 `up -d`**
- 야간 가동(전원 PC): 절전·최대 절전 해제, Windows Update 일시 중지(사용 시간 08:00~02:00), Docker Desktop 로그인 시 자동 시작, VM 헤드리스 자동 시작. 8GB 이하 PC는 `.wslconfig` `memory=4GB`
- 아침 점검(Zabbix·MCP 담당, 08:50): VM 호스트 PC IP 확인 → VM 동작 → `apiinfo.version` → 최근 데이터 2분 이내 → 바뀌었으면 데모 호스트 `.env` `ZABBIX_URL` 수정 후 `up -d`, #1-서버 공지
- 백업: 매일 09:00·스키마 변경 전·리허설 직전·10/16 11:30 골든. 복원은 `stop → cp → start`. `backups/`는 git 제외
- 포트: 데모 호스트 PC 8080 인바운드, VM 호스트 PC 8081·10051 인바운드. 8080·8000이 겹치면 compose 호스트 포트만 바꾸고 `APP_BASE_URL`을 맞춘다
- 시간대: 컨테이너·DB UTC, 화면만 KST. Windows 시간 동기화 켜기(STALE 판정 정확도)
- 줄바꿈: `.gitattributes`로 LF 고정, `*.ps1`만 CRLF. 컨테이너에서 도는 `.sh`가 CRLF면 깨진다

## 하지 않는 것
- Zabbix 서버를 compose에 포함, DB 컨테이너 추가(PostgreSQL 등 없음), 바인드 마운트
- Backend·Agent·MCP 호스트 포트 공개
- `.env` 커밋·값 기록. 여기 문서에는 변수 **이름**만
- 장애 주입 스크립트를 야간에 실행(야간 루프도 금지), 디스크 주입은 상한(20GB·여유 10%·`%TEMP%\dejafix-fill\`만) 없이 실행
- 데모 전 `main` 동결 이후 compose 변경(팀장 승인 없이는 금지)

## 테스트·확인 (PR 머지 조건)
- `docker compose -f infra/docker-compose.yml config` 통과(`.env`가 없으면 `.env.example`을 복사한 임시 `.env`로)
- `docker compose up -d --build` 후 `ps`에 5개 Up, 공개 포트 8080만. `docker compose exec agent kill 1`로 주 프로세스를 죽이면 자동 재시작(FR-INF-001 T)
- `docker compose exec backend ls /data`에 `shared.db`·`backend.db`(FR-DATA-001)
- `backup-db.ps1` 실행 → 파일 2개, `PRAGMA integrity_check` ok, 복원 후 로그인 가능(FR-INF-006)
- 주입 → 정리 1회 시험: 작업 관리자 CPU ≥ 85% 후 자동 종료, `cleanup.ps1` 후 부하 프로세스 0개(FR-INF-003·005)

## 데모 기준
데모 호스트 PC에서 compose로 5개 서비스 기동, 주입 → 화면 → 메일 **3분 안에 2회 연속**(B6 DoD). 11:00까지 Zabbix 불안정이면 `ZABBIX_MOCK=true`, 13:00까지 compose 불안정이면 로컬 프로세스.
