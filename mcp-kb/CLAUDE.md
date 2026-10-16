# mcp-kb — RAG 지식 검색 MCP 서버 (streamable HTTP `:8300/mcp`, 내부 전용, [이후])

주담당 팀장 · 부담당 Zabbix·MCP 담당 (결정 017). 먼저 읽을 것: 루트 `CLAUDE.md` → `contracts/mcp-tools.md` 6장 → `libs/kb/CLAUDE.md`.

- 도구는 `kb_search_knowledge` **하나만** 등록한다(쓰기 도구 없음, SAFE-03). 응답은 `contracts/mcp-tools.md` 2장 공통 봉투
- `knowledge.db`는 **읽기 전용**으로 연다. 색인(쓰기)은 `python -m dejafix_kb index`만 한다
- 하지 않는 것: Zabbix·shared.db 호출, LLM 호출, 티어 판단, 키·IP 로그 출력
- 환경 변수(이름만): `KB_DB_PATH`, `KB_ROOT`, `KB_EMBED_MODEL`, `KB_EMBED_BASE_URL`, `KB_EMBED_API_KEY`, `KB_MIN_COSINE`, `MCP_KB_HOST`, `MCP_KB_PORT`, `INTERNAL_TOKEN`(선택)
- 실행: `uv run --package mcp-kb python -m mcp_kb` (`:8300/mcp`, `GET /healthz`)
- 테스트: `uv run pytest mcp-kb`
