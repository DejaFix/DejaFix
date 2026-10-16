# libs/kb — RAG 장애 대응 지식 도우미 (결정 017, [이후])

주담당 팀장 · 부담당 DB·메일 담당. 먼저 읽을 것: 루트 `CLAUDE.md` → `docs/decisions/017-rag-knowledge-assistant.md`.

- 하는 일: 지식 출처 수집(FR-RAG-002) → 청킹(FR-RAG-003) → `knowledge.db` 저장(DR-RAG-001) → 임베딩(FR-RAG-004) → 하이브리드 검색(FR-RAG-005)
- 하지 않는 것: shared.db·backend.db 쓰기(읽기만), Zabbix 호출, LLM 답변 생성, 티어 판단, 엔진 코드에 IT 전용 키·동작 ID 하드코딩(팩 경로는 `DOMAIN_PACK`으로만)
- 비밀값은 환경 변수로만 받고 로그·청크에 남기지 않는다(NFR-RAG-001)
- 환경 변수(이름만): `KB_ROOT`, `KB_DB_PATH`, `KB_DOC_DIRS`, `SHARED_DB_PATH`, `BACKEND_DB_PATH`(해결 메모 읽기), `DOMAIN_PACK`, `KB_EMBED_BASE_URL`·`KB_EMBED_API_KEY`(비면 `LLM_*`), `KB_EMBED_MODEL`, `KB_EMBED_DIM`, `KB_EMBED_BATCH`, `KB_EMBED_PAUSE_SEC`, `KB_MIN_COSINE`
- 테스트: `uv run pytest libs/kb`
