# DejaFix

Zabbix 알람을 받아 AI가 장애 원인을 분석해주는 웹 서비스. 6명이 각자 Claude Code로 개발한다.

## 스택
- Backend: Python FastAPI
- Frontend: React + Vite
- DB: PostgreSQL
- 모니터링: Zabbix

## 규칙
- 자기 담당 폴더 밖의 파일은 수정 금지 (필요하면 담당자에게 요청)
- 경로는 항상 상대경로 사용
- 비밀값(토큰, 비밀번호, API 키)은 `.env`에만 저장, 커밋 금지
- `main` 브랜치 직접 푸시 금지 (브랜치 → PR)

## 폴더
frontend, backend, agent, mcp-zabbix, infra, contracts, packs/it, docs
