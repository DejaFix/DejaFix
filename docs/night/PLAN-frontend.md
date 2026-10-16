# PLAN-frontend — 화면 작업 큐 (담당 화면 담당, 부 연동·인프라 담당 / 폴더 `frontend/`만)

- 기준: `frontend/CLAUDE.md`, `docs/mvp-checklist.md` "Frontend", `contracts/api.md`(머지되면 우선), 기획서 4-2
- 항목마다 `npm run lint && npx tsc --noEmit && npm run build` 통과 후 커밋 1개. 실패 2번이면 `[BLOCKED]` + `LOG-frontend.md`
- 원칙: 화면 구성은 살리고 데이터 형식만 계약으로. 범위 밖 화면(`/cost`, `/compare`, 평소 범위·디스크 예측·히트맵, `/plans`·`/reports`·`/alerts`·`/admin`)은 손대지 않는다. 자잘한 수정은 `docs/ui-backlog.md`
- 타입·API 클라이언트·MSW·`UnknownValue`·`EvidenceTrace`·어시스턴트 패널은 `PLAN-frontend-api.md`(연동·인프라 담당) 쪽 큐다. 여기서는 그 결과를 **쓰기만** 한다. 아직 없으면 임시 목 타입으로 두고 LOG에 적는다

## 작업 큐
- [x] **1. 로그인 화면** (FR-FE-001): `admin`/`oncall` 폼, 잘못된 비밀번호 오류 문구, 성공 시 현황 홈 이동 2초 안. 토큰 저장은 `AuthProvider`(frontend-api 큐 6번)가 맡는다
- [ ] **2. 공통 레이아웃·연결 상태** (FR-FE-002): 헤더 "DejaFix · Zabbix AI", 메뉴(현황 홈·장애·AI 어시스턴트 + [선택]·[이후] 메뉴는 "준비 중"), 상단 연결 상태 뱃지(zabbix·agent·mcp_zabbix·shared_db). Zabbix 끊기면 15초 안 경고 배너
- [ ] **3. "준비 중" 메뉴** (FR-FE-013): 비용 절감·서버 비교 메뉴 클릭 시 "준비 중" 안내, API 호출 없음. 기존 화면 코드는 그대로 두고 라우팅만 안내 페이지로
- [x] **4. 현황 홈 KPI 4종** (FR-FE-003): `KpiCard` 4개 — 활성 장애, High 이상, 감시 호스트(정상/전체, 확인 불가 별도), 오늘 리포트 수·평균 분석 시간. 값은 `Measured`, `unknown`이면 `UnknownValue`(0으로 보이면 안 됨)
- [x] **5. 현황 홈 장애 목록** (FR-FE-004): 새 장애/오래된 장애, 심각도 칩·호스트·시작 시각(KST)·분석 상태 배지(`skipped/pending/running/done/fallback/failed`). 클릭 → `/incidents/:id`. 15초 폴링은 react-query 설정(frontend-api)
- [x] **6. 장애 상세 — 리포트 영역** (FR-FE-006): 요약·영향 범위·원인 TOP3(확신도 **low/medium/high 문자**)·확인할 수 없음 목록(사유 코드)·사람이 확인할 것. `kind=fallback`이면 "LLM 미연결/실패 — 규칙 기반 최소 리포트" 라벨. 기존 "검증 결과(확인/반증)" 표시는 계약에 없으므로 확신도·근거로 교체. **다시 분석·메일 재발송·검토 버튼은 렌더하지 않는다**
- [x] **7. 장애 상세 — 계획 미리보기·ReadOnlyNotice** (FR-FE-008): 단계마다 티어 배지(A 초록 "조회 · 안전" / B 주황 "변경 · 승인 필요(미구현)" / C 빨강 "금지 · 사람이 판단"), `command_preview`·`precheck`·`expected_effect`·`risk`·`rollback`. 상단 ReadOnlyNotice. **"실행/Run/Execute" 라벨의 button·a·input 금지**. 계획이 없으면 "계획 생성 실패/없음" 표시
- [x] **8. 장애 상세 — 메일 발송 기록** (FR-FE-009): 하단에 `mail_logs[]`(수신자·sent/failed/skipped·시도 횟수·시각 KST·실패 오류 요약)
- [ ] **9. 마무리 점검**: DOM 검색으로 실행 요소 0개, 모든 `null`이 `UnknownValue`로, 확신도 퍼센트 없음, 메뉴 "준비 중" 동작 — 결과를 LOG에 기록
