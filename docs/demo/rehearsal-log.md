# 리허설 측정 기록 (T76, NFR-PERF-001·NFR-OBS-008·NFR-EVAL-002)

`docs/demo/README.md` "리허설 측정 기록"의 누적 기록 파일이다. 회차마다 한 행을 **맨 아래에** 추가한다.

## 기록 규칙
- 시각은 KST `HH:MM:SS`. 화면·메일·DB에서 **직접 본 시각만** 적고, 못 본 칸은 `확인 못 함`으로 둔다(추정 값을 적지 않는다).
- 주입은 `infra/scripts/inject-cpu.ps1 -Minutes 3`(데모 PC), 끝나면 `cleanup.ps1` exit 0 확인.
- 각 칸의 기준
  - **Problem 발생**: Zabbix 웹 Monitoring → Problems의 시작 시각 (`DejaFix demo: CPU 1분 평균 85% 초과`, High)
  - **`incidents` 행**: `shared.db` `incidents.first_seen_at` (Scheduler가 처음 본 시각)
  - **리포트 저장**: `analysis_reports.created_at` (Agent)
  - **화면 표시**: 현황 홈에 장애가 처음 보인 시각(15초 폴링)
  - **메일 도착**: 수신함 도착 시각(`MAIL_PROVIDER=console`이면 `mail_logs.sent_at`, 비고에 표시)
  - **총 소요**: 주입 시작 → 메일 도착
- 리포트 종류: `llm` / `fallback` (`analysis_reports.kind`)
- 원인 TOP3 정답 포함: 리포트 원인 후보에 "CPU 부하 프로세스"가 있으면 `예`, fallback이면 `해당 없음`(원인을 판단하지 않음)

## 합격선과 조정 순서
- **3분 이내 2회 연속** (NFR-PERF-001). 데모 트리거 단독 목표는 주입 후 120초 이내(NFR-PERF-006, 결정 016 — 팀 서버 첫 실측 104초, Issue #60).
- 넘으면 ① 메일 워커 30→15초 ② Agent 워커 10→5초 ③ 데모 트리거 창 1m→30s 순서로 하나씩 바꾸고, 바꾼 내용을 비고에 적는다.

## 기록

| 회차 | 일시(KST) | 데모 PC | 주입 시작 | Problem 발생 | `incidents` 행 | 리포트 저장 | 화면 표시 | 메일 도착 | 총 소요 | 감지 여부 | 리포트 종류 | 원인 TOP3 정답 포함 | 비고 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2026-10-16 15:22 | TaeYoon-PC (팀장 PC, 데모 PC 아님) | 15:22:38 | 15:24:33 (+115초) | 15:24:50 (+132초) | 15:25:11 (+153초) | 확인 못 함 | 15:25:37 (+179초) | **2분 59초** | 예 | llm | 예 | 로컬 프로세스 실행(compose 아님), 팀 Zabbix 실서버·LLM Gemini `gemini-3.5-flash-lite`. Problem 시각은 `incidents.started_at`(problem.clock). 메일은 `MAIL_PROVIDER=console`이라 `mail_logs.sent_at`. 원인 1위 '고부하 프로세스 실행'(high, 근거 2개), 계획 2단계 모두 A(최고 A), Agent 도구 호출 6회 모두 ok. 트리거 115초로 결정 016 목표(120초) 안. `cleanup.ps1` exit 0. 합격선 2회 연속 중 1회째 |

## 참고
- 10/15 E2E 관통(T69) 결과는 결정 기록 `docs/decisions/015`(PR #91)에 있다. 그 실행은 `ZABBIX_MOCK=true`라 주입→Problem 구간이 없어 이 표에 넣지 않는다.
