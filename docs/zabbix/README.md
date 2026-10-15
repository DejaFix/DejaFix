# docs/zabbix — Zabbix 조사 결과, API 정리

## 문서

| 파일 | 내용 |
|---|---|
| `core-metrics.md` | **먼저 볼 것.** CPU / MEM / DISK / Network 핵심 지표: Item key, 단위, 템플릿 장애 기준, API로 가져오는 순서 |
| `windows-agent-api.md` | 전체 명세: Windows 에이전트 설치·수집 검증(116개 key), Zabbix 7.0 조회 API 7개, 실서버 응답(12.0절) |
| `api-requests/` | 조회 API 요청 본문 예시 10개 (JSON-RPC) |
| `verification/` | 검증 결과: 패시브 key별 결과, 액티브 이벤트 로그 표본, 로컬 실서버 API 응답(`api-probe-2026-10-14/`) |

## 플랫폼 구성에서의 위치 (멘토 구성도 기준)

운영 Zabbix를 조회하는 서비스는 셋이다. 이 폴더의 조사는 셋 모두의 기반이다.

| 조회하는 서비스 | 쓰는 API | 참고 |
|---|---|---|
| Zabbix MCP (장애·서버·지표·알림 설정 조회, 쓰기 도구 없음) | problem/event/trigger.get, host.get, item/history.get | 알림 설정(action.get, mediatype.get)은 아직 미조사 |
| Backend (대시보드·리포트) | item.get → history.get, problem.get → trigger.get | `infra/zabbix/tools/dashboard/`가 같은 순서로 동작하는 시제품 |
| Scheduler (하루 한 번 지표·서버 사양 수집) | trend.get, item.get | trend는 숫자형만, 1시간 단위, 최대 2시간 지연, 정렬 없음 |

공통 규칙
- 인증은 `Authorization: Bearer <토큰>` 헤더. 본문 `auth`는 7.2에서 삭제됐다.
- 토큰 사용자는 읽기 전용 역할(API 허용 목록에 get 메서드만)로 만든다. 로컬에서 `user.get`이 차단되는 것을 확인했다.
- `history.get`은 value_type 하나씩만 조회한다(기본값 3).
- `problem.get`은 호스트를 주지 않는다 → `event.get`(`selectHosts`)이나 `trigger.get`(`selectHosts`)을 한 번 더 부른다.
- 지표 분류는 key 이름 대신 템플릿의 `component` 태그(cpu / memory / storage / network)로 조회할 수 있다(Windows 템플릿에서 확인, Linux는 미검증).
