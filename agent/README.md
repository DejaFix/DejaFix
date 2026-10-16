# agent

장애를 분석하는 AI Agent (FastAPI :8100, 내부 전용). 10초마다 `shared.db`의 새 장애를 골라 Zabbix MCP로 조회만 하고, 리포트(원인 후보 TOP3·영향 범위·근거)와 변경 계획(미리보기)을 만들어 저장한다. 계획의 티어(A/B/C)는 `packs/<domain>/actions.yaml`과 코드가 정하고 LLM은 정하지 않는다. LLM이 없어도 fallback 리포트·계획으로 흐름이 이어진다. 채팅(`/v1/chat` SSE)도 여기서 답한다.

규칙·실행·테스트는 `CLAUDE.md`. 계약은 `contracts/agent-api.md`(제공)·`contracts/mcp-tools.md`(소비).
