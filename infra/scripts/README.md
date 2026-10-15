# infra/scripts

Windows PowerShell 운영 스크립트 (담당 이재헌, 부 이태윤 / 백업은 노예진). `*.ps1`은 CRLF(`.gitattributes`).

| 스크립트 | 등급 | 내용 | 근거 |
|---|---|---|---|
| `inject-cpu.ps1` | 필수 | `-Minutes N`(기본·최대 10) 코어 수만큼 CPU 부하, 만료·Ctrl+C 시 종료 | FR-INF-003, G12 |
| `cleanup.ps1` | 필수 | 주입 프로세스 종료, `%TEMP%\dejafix-fill\` 삭제 | FR-INF-005 |
| `backup-db.ps1` | 필수 | SQLite 백업 API로 `shared.db`·`backend.db` → `backups/`, 최근 5개 | FR-INF-006, 11-3 |
| `inject-disk.ps1` | 선택 | 90% 도달에 필요한 양만, 상한 20GB·여유 10%, `%TEMP%\dejafix-fill\`에만 | FR-INF-004 |
| `check-env.ps1` | 선택 | 아침 점검 5단계(IP·VM·`apiinfo.version`·최근 데이터·`.env` 공지) | FR-INF-010, 11-2 |

- 장애 주입 스크립트는 야간에 실행하지 않는다. 야간 작업 루프도 실행 금지.
