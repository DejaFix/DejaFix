# DejaFix

Zabbix 알람을 받아 AI가 장애 원인을 분석해주는 웹 서비스.

## 구조
| 폴더 | 설명 |
|---|---|
| frontend | React + Vite 웹 UI |
| backend | FastAPI 백엔드 |
| agent | 장애 분석 AI 에이전트 |
| mcp-zabbix | Zabbix 연동 MCP 서버 |
| infra | 배포/인프라 |
| contracts | 모듈 간 계약(스키마) |
| packs/it | IT 장애 도메인 팩 |
| docs | 문서 |

## 시작
1. `.env.example`을 `.env`로 복사 후 값 채우기
2. 각 폴더의 `CLAUDE.md` 참고

규칙은 루트 `CLAUDE.md` 참고.
