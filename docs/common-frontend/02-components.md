# 02. 컴포넌트 카탈로그

위치: `frontend/src/components/`. 범용 = 도메인 없이 그대로 가져감 / 패턴 = 구조만 참고.

## 1. 범용 컴포넌트

| 컴포넌트 | 파일 | 역할 | props | 메모 |
|---|---|---|---|---|
| `Icon` | `Icon.tsx` | 선 아이콘(SVG, `currentColor`) | `name: IconName`, `size=18` | 아이콘 이름 표(`paths`)에 추가해 확장. `aria-hidden` |
| `Collapsible` | `Collapsible.tsx` | 접이식 섹션 | `title`, `count?`, `meta?`, `defaultOpen=false`, `id?`, `children` | 버튼에 `aria-expanded`. 열려 있을 때만 children을 렌더 |
| `EChart` | `EChart.tsx` | ECharts 래퍼 | `option`, `tall=false` | 필요한 차트·컴포넌트만 `echarts/core`로 등록(번들 절약). **`option`은 호출 쪽에서 `useMemo`로 고정**, 크기 변화는 `ResizeObserver` |
| `UserMenu` | `UserMenu.tsx` | 헤더 사용자 칸 + 로그아웃 팝업 | `name`, `role`, `onLogout` | 바깥 클릭·`Esc`로 닫힘, `aria-haspopup="menu"` |
| `Layout` | `Layout.tsx` | 앱 셸(사이드바·헤더·패널·`<Outlet/>`) | 없음(훅으로 데이터) | **`nav` 배열만 바꿔서 재사용**. `soon: true`면 "준비 중" 칩, `adminOnly`는 역할로 필터. 사이드바 접힘은 `localStorage`(민감하지 않은 값만) |
| `ComingSoon` | `pages/ComingSoon.tsx` | "준비 중" 안내 | `title` | 메뉴는 있으나 기능이 없을 때. API를 부르지 않는다 |
| `Chips` | `Chips.tsx` | 칩 모음 | `SeverityChip`, `RiskBadge`, `VerdictChip`, `UnknownValue({label})` | 색은 `.chip.<변형>`. 라벨 표는 `lib/format.ts` |

## 2. 도메인 조각 (패턴으로 참고)

| 컴포넌트 | 파일 | 보여 주는 것 | 재사용 포인트 |
|---|---|---|---|
| `Unknown` | `IncidentParts.tsx` | "확인할 수 없음 · 사유 · 수집 시각" | **값이 없을 때 쓰는 단일 표시.** 사유 코드(`NO_DATA`·`STALE`·`TOOL_ERROR`·`NO_PERMISSION`·`NOT_COLLECTED`)와 시각을 같이 보여 준다 |
| `SeverityInfoChip` · `AnalysisBadge` · `ConfidenceChip` · `TierBadge` | `IncidentParts.tsx` | 심각도·분석 상태·확신도(낮음/보통/높음)·조치 등급 A/B/C | **상태값 → `{label, 칩 클래스}` 표**로 만드는 방식이 핵심(`Record<Enum, {label, cls}>`) |
| `EvidenceIds` · `EvidencePanel` | `IncidentParts.tsx` | 근거 ID 칩 → 눌러서 도구 호출 기록(인자·결과 요약·호출/데이터 시각) 펼침 | "AI가 무엇을 보고 말했나"를 추적하는 UI. 기록에 없는 ID는 눌리지 않게 |
| `PlanStepCard` | `IncidentParts.tsx` | 계획 한 단계(명령 미리보기·사전 확인·위험·롤백·등급) | **실행 버튼이 없다.** 보여 주기만 |
| `MailLogRow` | `IncidentParts.tsx` | 메일 발송 기록 한 줄 | 상태 표 + 실패 사유 |
| `ConnectionStatus` · `ZabbixBanner` | `ConnectionStatus.tsx` | 구성요소 연결 상태 칩 / 끊김 경고 배너(`role="alert"`) | 상태값을 못 받으면 추정하지 않고 "확인할 수 없음" |
| `UrgentBanner` · `SystemList` | `TopStatus.tsx` | 헤더의 가장 급한 항목 한 줄 / 사이드바 하단 시스템 상태 | 정렬 기준·"지연" 판정(`STALE_MS`) 예시 |
| `FocusCard` | `FocusCard.tsx` | 선택한 항목을 ① 무엇이 ② 왜 ③ 어떻게 + 처리 흐름으로 | 상세 응답 한 번으로 요약 카드를 만드는 구성 |
| `AssistantPanel` | `AssistantPanel.tsx` | 우측 AI 채팅 패널 | 말풍선·제안 질문 칩·입력·`Esc` 닫기. 상태는 `state/assistant.ts` 컨텍스트 |
| `EvidenceTrace` | `EvidenceTrace.tsx` | 채팅 답변 밑 "도구 N회" 접이식 | 옛 `EvidenceCall` 모양을 써서 `EvidencePanel`과 모양이 다르다. 새 프로젝트는 하나로 합친다 |

보조: `incidentFormat.ts`(`kstShort`: UTC ISO → `MM-DD HH:mm`(KST), `analysisNotes`: 상태별 안내 문구).

## 3. 공통 CSS 클래스 (`global.css`)

| 분류 | 클래스 |
|---|---|
| 레이아웃 | `.shell` `.sidebar` `.main` `.topbar` `.page` `.page-head` `.page-title` `.page-sub` `.crumb` |
| 카드·그리드 | `.card` `.card-head` `.card-title` `.card-sub` `.grid` `.grid.kpi`(4열) `.grid.two`(2열) `.kpi-card` `.kpi-label` `.kpi-value` `.kpi-hint` |
| 버튼·입력 | `.btn` (`.primary` `.dark` `.small`) `.seg`(토글 묶음) `.search` `.field` `.select` `.switch` `.pick` `.toolbar` |
| 상태 | `.chip.<변형>` `.note`(`.warn`) `.toast` `.dot` `.unknown`(앞에 "—") `.mock-chip` |
| 목록·표 | `.alert-row` `.list-row` `.group-row` `table.data`(`td.num` 오른쪽 정렬) `.tile`(`.sev-*`) |
| 장애 상세 | `.detail-grid` `.cand`(원인·단계 카드) `.evidence` `.step` `.cmd` `.rollback` `.timeline` `.kv` `.dsum-*`(3칸 요약) |
| AI 패널 | `.assistant` `.bubble.user/.ai` `.q-chip` `.composer` `.send` `.typing` |
| 로딩·빈 화면 | `.skeleton` `.skeleton-line` `.empty` |
| 차트 | `.chart` `.chart.tall` |
| 셸(`shell.css`) | `.side-top` `.hamburger` `.nav-item` `.nav-badge` `.nav-soon` `.syslist-*` `.urgentbar` `.usermenu-*` `.bell` `.shell.collapsed` |

## 4. 컴포넌트를 새로 만들 때 규칙

- 색은 토큰으로만(`var(--…)`), 새 변형은 `.chip.<이름>`처럼 **클래스 이름으로** 추가한다.
- 상태값 → 라벨·색은 `Record<상태, {label, cls}>` 표 하나로 두고 분기문을 흩뿌리지 않는다.
- 값이 없을 수 있으면 반드시 `Unknown`을 쓴다(04 문서). 빈칸·0·`null` 글자 금지.
- 컴포넌트 파일은 **컴포넌트만 export**한다(상수·함수는 `lib/`로). `react-refresh/only-export-components` 린트 때문이다.
- 아이콘은 `Icon`에 추가하고, 글자 없는 버튼에는 `aria-label`을 단다.

## 5. 페이지 목록 (`src/pages`, 라우트는 `App.tsx`)

| 라우트 | 파일 | 상태 |
|---|---|---|
| `/login` | `Login.tsx` | 실제 인증 |
| `/` | `Dashboard.tsx` | 실제 API(KPI·장애 목록) + 일부 카드는 목 |
| `/incidents/:id` | `IncidentSummary.tsx` = 위에 `FocusCard`(요약 3칸) + 아래에 `IncidentDetail.tsx`(`embedded`, 리포트·근거·계획·메일. 조각은 `IncidentParts`) | 실제 API |
| `/plans`, `/plans/:id` | `Plans.tsx`, `PlanDetail.tsx` | 이후 범위(목) |
| `/reports` · `/alerts` · `/admin` | `Reports.tsx` · `Alerts.tsx` · `Admin.tsx` | 이후 범위(목), 관리자는 `adminOnly` |
| `/cost` · `/compare` | `ComingSoon` | 준비 중(원본 `Cost.tsx`·`ServerCompare.tsx`는 코드만 보관) |

> 페이지 내부 구현은 이 문서에서 다루지 않는다. 가져갈 때는 Dashboard·상세 화면의 **구성**(KPI 4 + 목록 + 요약 카드)만 참고하는 것을 권한다.
