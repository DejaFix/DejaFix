# infra

배포 및 인프라 설정 (Docker Compose, 장애 주입·운영 스크립트 등)

- DB는 SQLite 2파일(`shared.db`, `backend.db`)을 named volume `dejafix-data`(`/data/`)에 둔다. 별도 DB 컨테이너는 없다(PostgreSQL 사용 안 함).
- Windows 폴더 바인드 마운트는 SQLite WAL 잠금이 불안정하므로 쓰지 않는다.
- 운영 Zabbix는 Ubuntu VM의 외부 서비스라 `docker-compose.yml`에 넣지 않는다.
- `scripts/`: 장애 주입·정리·아침 점검·DB 백업 스크립트 (기획서 3-6, 11장)
