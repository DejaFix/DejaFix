// 타입은 네 구역으로 나뉜다.
// 1) API 계약 타입 — docs/plan.md 7장·5-5, docs/requirements.md 6-2, 노션 프론트 API 요청서 3장 기준. 새 코드는 이것만 쓴다.
// 2) 인증 — #1·#3 (PR #10)
// 3) Legacy — 지금 화면(목업)이 쓰는 옛 타입. 화면 이전이 끝나면 지운다. @deprecated
// 4) 이후 — 범위 밖 화면(비용 절감·서버 비교·알림·관리자·현황 홈 차트 5종)용. 금요일 MVP에서는 그대로 둔다.
// 시각 필드는 전부 UTC ISO 8601 문자열(예: '2026-10-16T01:20:00Z'). KST 변환은 화면에서 한다.

// ============================================================================
// 1) API 계약 타입
// ============================================================================

// ---- 공통 봉투 (7장 공통) ----
export interface ApiResponse<T, M = Record<string, unknown>> {
  data: T
  meta: M
}

export type ApiErrorCode =
  | 'INVALID_CREDENTIALS'
  | 'UNAUTHORIZED' // 요청서 확인 요청 5
  | 'FORBIDDEN' // 요청서 확인 요청 5
  | 'NOT_FOUND' // 요청서 확인 요청 5
  | 'ZABBIX_UNAVAILABLE'
  | 'AGENT_UNAVAILABLE' // 요청서 확인 요청 5
  | 'NOT_IMPLEMENTED'
  | (string & {})

export interface ApiErrorBody {
  error: { code: ApiErrorCode; message: string }
}

export interface ListMeta {
  next_cursor: string | null
}

// ---- 확인할 수 없는 값 (7장 공통 Measured, SAFE-10) ----
export type UnknownReason = 'NO_DATA' | 'STALE' | 'TOOL_ERROR' | 'NO_PERMISSION' | 'NOT_COLLECTED'

/** 화면에 숫자로 보이는 값의 공통 타입. unknown=true면 value는 null이고 UnknownValue로 그린다(0·빈칸 금지). */
export interface Measured {
  value: number | null
  unit: string
  collected_at: string
  unknown: boolean
  unknown_reason?: UnknownReason
}

// ---- 심각도 (5-5) ----
export type SeverityLevel = 0 | 1 | 2 | 3 | 4 | 5
export type SeverityLabel = 'Not classified' | 'Information' | 'Warning' | 'Average' | 'High' | 'Disaster'

/**
 * Zabbix 심각도 `{level, label}` (5-5). #6·#10·#11 공통(요청서 확인 요청 1).
 * 이름이 `Severity`가 아닌 이유: 지금 components/Chips.tsx·pages/Dashboard.tsx가 옛 문자열 `Severity`를 import한다.
 * 화면 이전이 끝나면 `Severity`로 이름을 넘겨받는다.
 */
export interface SeverityInfo {
  level: SeverityLevel
  label: SeverityLabel
}

export interface Tag {
  tag: string
  value: string
}

// 호스트 보강(Scheduler trigger.get selectHosts) 전에는 null — 화면은 UnknownValue로 (contracts/incident.schema.json)
export interface HostRef {
  id: string | null
  name: string | null
}

// ---- #4 GET /api/health ----
export type ComponentStatus = 'ok' | 'down' // 요청서 확인 요청 2

export interface Health {
  zabbix: ComponentStatus
  agent: ComponentStatus
  mcp_zabbix: ComponentStatus
  shared_db: ComponentStatus | 'waiting' // Agent가 아직 shared.db를 만들기 전이면 waiting
  backend_db: ComponentStatus
  scheduler_last_ok: string | null // scheduler_jobs.poll_problems.last_ok_at, 기록 없으면 null
}

export interface HealthMeta {
  checked_at: string
}

// ---- #5 GET /api/dashboard/summary ----
export interface DashboardSummary {
  active_incidents: Measured
  high_incidents: Measured // severity 4(High)·5(Disaster)
  hosts: { ok: Measured; total: Measured; unknown: Measured }
  reports_today: Measured // "오늘" = KST 자정 기준(요청서 확인 요청 3)
  avg_analysis_sec: Measured
  llm_usage_today?: Measured | null // [선택]
}

export interface DashboardSummaryMeta {
  generated_at: string
}

// ---- #6 GET /api/problems (Zabbix 실시간) ----
export interface Problem {
  eventid: string
  name: string
  severity: SeverityInfo
  clock: string
  host: HostRef
  tags: Tag[]
  incident_id: number | null // 아직 DejaFix가 수집하지 않았으면 null
}

export interface ProblemsMeta {
  collected_at: string
  truncated: boolean
}

// ---- #10 GET /api/incidents, 표준 Incident (5-5) ----
export type IncidentStatus = 'problem' | 'resolved'
export type AnalysisStatus = 'skipped' | 'pending' | 'running' | 'done' | 'fallback' | 'failed'

export interface IncidentAnalysis {
  status: AnalysisStatus
  report_id: number | null
  plan_id: number | null
}

export interface Incident {
  id: number
  source: 'zabbix'
  zabbix: { eventid: string; triggerid: string; hostid: string | null }
  host: HostRef
  title: string
  severity: SeverityInfo
  status: IncidentStatus
  started_at: string
  resolved_at: string | null
  tags: Tag[]
  analysis: IncidentAnalysis // 저장 컬럼이 아니라 Backend가 JOIN으로 채움
}

// ---- #11 GET /api/incidents/{id} — 장애 상세 ----
export type Confidence = 'low' | 'medium' | 'high' // 퍼센트·점수 금지(SAFE-11)

export interface Cause {
  rank: number
  title: string
  confidence: Confidence
  reasoning: string
  evidence_ids: string[]
  verify: string // 사람이 확인할 방법
}

export interface ReportImpact {
  hosts: string[]
  services: string[]
  user_impact: string | null // fallback 리포트는 null일 수 있다(agent-api.md 리포트 스키마, db-schema.sql impact_json)
  evidence_ids: string[]
}

export interface Fact {
  label: string
  value: number | string | null // 근거가 없으면 null + unknown_reason(SAFE-08)
  unit: string | null
  unknown_reason: UnknownReason | null
  evidence_ids: string[]
  collected_at: string | null
}

export interface UnknownItem {
  label: string
  reason: UnknownReason
}

export interface AnalysisReport {
  id: number
  version: number
  kind: 'llm' | 'fallback' // fallback이면 "LLM 미연결/실패 — 규칙 기반 최소 리포트" 라벨
  summary: string
  impact: ReportImpact
  causes: Cause[] // 최대 3개
  facts: Fact[]
  unknowns: UnknownItem[]
  next_checks: string[]
  created_at: string
}

/** 근거 = 리포트가 참조하는 run의 tool_calls 1행(result_json 제외). EvidenceTrace가 그린다(SAFE-12). */
export interface Evidence {
  id: string // 'ev_' + 짧은 id
  tool: string
  args: Record<string, unknown>
  ok: boolean
  duration_ms: number | null
  result_summary: string | null
  data_clock: string | null
  called_at: string
}

export type Tier = 'A' | 'B' | 'C'

/** 변경 계획(미리보기). 실행 필드가 없고 mode는 항상 'preview'다(SAFE-04). */
export interface ChangePlan {
  id: number
  title: string
  goal: string | null
  mode: 'preview'
  max_tier: Tier
  assumptions: string[]
}

/** 계획 단계. tier는 코드가 actions.yaml로 판정한 값만 온다(SAFE-06). B 단계는 precheck·rollback이 있다(SAFE-07). */
export interface PlanStep {
  seq: number
  action_id: string | null
  title: string
  target: string | null
  command_preview: string | null // 보여 주기만 하는 명령 예시
  tier: Tier
  rationale: string | null // 판정 근거·강등 사유
  precheck: string | null
  expected_effect: string | null
  risk: string | null
  rollback: string | null
  evidence_ids: string[]
}

export interface MailLog {
  id: number
  kind: 'incident_report' | 'manual' | 'test'
  recipient: string
  status: 'sent' | 'failed' | 'skipped'
  attempts: number
  error: string | null
  created_at: string
  sent_at: string | null
}

/** #11 응답 하나로 장애 상세 화면 전체를 그린다. 리포트가 아직 없으면 report·plan은 null, evidence·steps는 빈 배열(요청서 확인 요청 8). */
export interface IncidentDetail {
  incident: Incident
  report: AnalysisReport | null
  evidence: Evidence[]
  plan: ChangePlan | null
  steps: PlanStep[]
  mail_logs: MailLog[]
}

// ---- #18 POST /api/chat — SSE(7-2)와 비스트리밍 대체 응답 ----
export interface ChatRequest {
  conversation_id?: string
  message: string
  context: { incident_id?: number; hostid?: string }
}

/** SSE 이벤트. token은 LLM 응답일 때만, tool_call·tool_result는 도구를 부른 경우만 온다(meta → final만 와도 정상). */
export type ChatEvent =
  | { event: 'meta'; data: { conversation_id: string; run_id: string; message_id: number } }
  | { event: 'tool_call'; data: { id: string; tool: string; args: Record<string, unknown>; started_at: string } }
  | {
      event: 'tool_result'
      data: { id: string; ok: boolean; duration_ms: number; summary: string; data_clock: string | null }
    }
  | { event: 'token'; data: { text: string } }
  | {
      event: 'final'
      data: { message_id: number; content: string; evidence_ids: string[]; unknowns: UnknownItem[] }
    }
  | { event: 'error'; data: { code: string; message: string } }

export type ChatEventName = ChatEvent['event']

export interface ChatToolCall {
  id: string
  tool: string
  args: Record<string, unknown>
  ok: boolean
  duration_ms: number
  summary: string
  data_clock: string | null
}

/** 탈출 규칙 1: SSE가 막히면 같은 경로가 JSON으로 응답한다. conversation_id·message_id는 요청서 확인 요청 6. */
export interface ChatReply {
  conversation_id: string
  message_id: number
  content: string
  evidence_ids: string[]
  unknowns: UnknownItem[]
  tool_calls: ChatToolCall[]
}

// ============================================================================
// 2) 인증 — #1 POST /api/auth/login, #3 GET /api/auth/me (plan.md 7-1, IF-INT-BE-001·002)
// ============================================================================
export type Role = 'admin' | 'operator' | 'viewer'

export interface AuthUser {
  id: number
  username: string
  role: Role
  display_name: string | null
  email?: string | null
}

export interface LoginResult {
  token: string
  user: AuthUser
}

// ============================================================================
// 3) Legacy — 지금 화면(목업)이 쓰는 옛 타입. 새 코드에서 쓰지 않는다.
//    components/·pages/가 import하는 이름은 별칭으로 남겼다(이름을 바꾸면 화면이 깨지므로).
// ============================================================================

/** @deprecated 옛 문자열 심각도. 새 코드는 `SeverityInfo`(5-5)를 쓴다. */
export type LegacySeverity = 'info' | 'warning' | 'average' | 'high' | 'disaster'
/** @deprecated `LegacySeverity` 별칭. components/Chips.tsx·pages/Dashboard.tsx가 import한다. */
export type Severity = LegacySeverity

/** @deprecated 원인 후보 확인/반증. 계약은 `Cause.confidence`(low/medium/high) — 요청서 F8. */
export type LegacyVerdict = 'confirmed' | 'refuted' | 'unknown'
/** @deprecated `LegacyVerdict` 별칭. components/Chips.tsx가 import한다. */
export type Verdict = LegacyVerdict

/** @deprecated 계획 위험도. 계약은 `ChangePlan.max_tier`·`PlanStep.risk`(문장) — 요청서 F11. 비용 절감 화면도 쓴다. */
export type LegacyRisk = 'low' | 'medium' | 'high'
/** @deprecated `LegacyRisk` 별칭. components/Chips.tsx가 import한다. */
export type Risk = LegacyRisk

/** @deprecated 계획 상태. 계약 계획에는 없고 [선택] #15 reviews[]로 계산 — 요청서 F11. */
export type LegacyPlanStatus = 'draft' | 'reviewed' | 'discarded'
/** @deprecated `LegacyPlanStatus` 별칭. pages/PlanDetail.tsx가 import한다. */
export type PlanStatus = LegacyPlanStatus

/** @deprecated 현황 홈 장애 행. 계약은 `Incident`(#10)·`Problem`(#6) — 요청서 F5. */
export interface LegacyAlertItem {
  id: string
  name: string
  host: string
  project: string
  severity: LegacySeverity
  minutesOpen: number
  repeat24h: number | null
  group: 'new' | 'old'
}
/** @deprecated `LegacyAlertItem` 별칭. pages/Dashboard.tsx가 import한다. */
export type AlertItem = LegacyAlertItem

/** @deprecated 현황 홈 KPI. 계약은 `DashboardSummary`(#5, 값은 Measured) — 요청서 F4. */
export interface LegacySummary {
  newOpen: number
  repeating: number
  longOpen: number
  diskFullSoon: number
  openTotal: number
  serverTotal: number
  collectedAt: string
}

/** @deprecated 근거 호출. 계약은 `Evidence`(tool_calls 형식) — 요청서 F9. */
export interface LegacyEvidenceCall {
  tool: string
  command: string
  result: string
  ms: number
}
/** @deprecated `LegacyEvidenceCall` 별칭. components/EvidenceTrace.tsx·state/assistant.ts·api.ts가 import한다. */
export type EvidenceCall = LegacyEvidenceCall

/** @deprecated 원인 후보. 계약은 `Cause` — 요청서 F8. */
export interface LegacyCandidate {
  id: string
  title: string
  summary: string
  verdict: LegacyVerdict
  reason: string
  checks: LegacyEvidenceCall[]
}

/** @deprecated 타임라인. 계약에 없음 — started_at·report.created_at·mail_logs.sent_at으로 조립(요청서 F7). */
export interface LegacyTimelineEvent {
  at: string
  text: string
}

/** @deprecated 장애 상세. 계약은 `IncidentDetail`(#11) — 요청서 F7. */
export interface LegacyIncident {
  alert: LegacyAlertItem
  summary: string
  impact: string[]
  timeline: LegacyTimelineEvent[]
  candidates: LegacyCandidate[]
  planId: string | null
}

/** @deprecated 계획 단계. 계약은 `PlanStep`(tier·precheck·expected_effect·risk·rollback) — 요청서 F11. */
export interface LegacyPlanStep {
  command: string
  purpose: string
  rollback: string
}

/** @deprecated 계획. 계약은 `ChangePlan` + `PlanStep[]` — 요청서 F11. */
export interface LegacyPlan {
  id: string
  incidentId: string
  title: string
  status: LegacyPlanStatus
  risk: LegacyRisk
  impact: string[]
  steps: LegacyPlanStep[]
  createdAt: string
}

/** @deprecated 리포트. 계약은 `AnalysisReport`(구조화), 발송 여부는 `MailLog` — 요청서 F12. */
export interface LegacyReport {
  id: string
  incidentId: string
  title: string
  status: 'draft' | 'sent'
  createdAt: string
  sections: { heading: string; body: string }[]
}

/** @deprecated AI 답변. 계약은 `ChatEvent`(SSE)·`ChatReply`(비스트리밍) — 요청서 F14. */
export interface LegacyAssistantReply {
  text: string
  evidence: LegacyEvidenceCall[]
  unknowns: string[]
}
/** @deprecated `LegacyAssistantReply` 별칭. api.ts(askAssistant)가 쓴다. */
export type AssistantReply = LegacyAssistantReply

// ============================================================================
// 4) 이후 — 범위 밖 화면용(비용 절감·서버 비교·알림·관리자·현황 홈 차트 5종). 계약에 API가 없거나 [이후]다.
//    금요일 MVP에서는 손대지 않는다. 연결할 때 요청서 F6·F18~F21대로 바꾼다.
// ============================================================================

// 현황 홈 차트 5종(요청서 F6): 같은 알림 여러 서버, 평소와 다른 값, 디스크 고갈 예측, 14일 추이, 시간대 히트맵
export interface CrossServerGroup {
  id: string
  name: string
  serverCount: number
  hosts: string[]
}

export interface BaselineItem {
  host: string
  metric: string
  now: number
  baselineMin: number
  baselineMax: number
  unit: string
  sinceMinutes: number
}

export interface DiskForecast {
  host: string
  daysLeft: number | null
}

export interface TrendDay {
  label: string
  counts: Record<LegacySeverity, number>
}

// 서버 비교 /compare (요청서 F21)
export interface ServerMetric {
  host: string
  project: string
  cpu: number | null
  cpuBaselineMax: number | null
  memory: number | null
  disk: number | null
  swap: number | null
  ioMs: number | null
  openAlerts: number
  collectedAt: string
  cpuSeries: (number | null)[]
}

// 비용 절감 /cost (요청서 F20)
export interface CostItem {
  id: string
  host: string
  currentType: string
  avgCpu: number | null
  p95Cpu: number | null
  avgMemory: number | null
  recommendedType: string | null
  currentMonthly: number
  recommendedMonthly: number | null
  risk: LegacyRisk | null
  note: string
  evidence: LegacyEvidenceCall[]
}

// 알림 /alerts (요청서 F18)
export type DeliveryStatus = 'sent' | 'failed' | 'pending'

export interface NotificationRule {
  id: string
  name: string
  condition: string
  recipients: string
  enabled: boolean
}

export interface DeliveryLog {
  id: string
  at: string
  rule: string
  recipient: string
  status: DeliveryStatus
  detail: string
}

// 관리자 /admin (요청서 F19)
export interface UserAccount {
  id: string
  name: string
  role: Role
  active: boolean
  lastLogin: string
}
