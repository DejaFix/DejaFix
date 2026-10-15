export type Severity = 'info' | 'warning' | 'average' | 'high' | 'disaster'
export type Verdict = 'confirmed' | 'refuted' | 'unknown'
export type Risk = 'low' | 'medium' | 'high'
export type PlanStatus = 'draft' | 'reviewed' | 'discarded'

export interface AlertItem {
  id: string
  name: string
  host: string
  project: string
  severity: Severity
  minutesOpen: number
  repeat24h: number | null
  group: 'new' | 'old'
}

export interface Summary {
  newOpen: number
  repeating: number
  longOpen: number
  diskFullSoon: number
  openTotal: number
  serverTotal: number
  collectedAt: string
}

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
  counts: Record<Severity, number>
}

export interface EvidenceCall {
  tool: string
  command: string
  result: string
  ms: number
}

export interface Candidate {
  id: string
  title: string
  summary: string
  verdict: Verdict
  reason: string
  checks: EvidenceCall[]
}

export interface TimelineEvent {
  at: string
  text: string
}

export interface Incident {
  alert: AlertItem
  summary: string
  impact: string[]
  timeline: TimelineEvent[]
  candidates: Candidate[]
  planId: string | null
}

export interface PlanStep {
  command: string
  purpose: string
  rollback: string
}

export interface Plan {
  id: string
  incidentId: string
  title: string
  status: PlanStatus
  risk: Risk
  impact: string[]
  steps: PlanStep[]
  createdAt: string
}

export interface Report {
  id: string
  incidentId: string
  title: string
  status: 'draft' | 'sent'
  createdAt: string
  sections: { heading: string; body: string }[]
}

export interface AssistantReply {
  text: string
  evidence: EvidenceCall[]
  unknowns: string[]
}

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
  risk: Risk | null
  note: string
  evidence: EvidenceCall[]
}

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

export type Role = 'admin' | 'operator' | 'viewer'

// #1 POST /api/auth/login, #3 GET /api/auth/me (plan.md 7-1, IF-INT-BE-001·002)
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

export interface UserAccount {
  id: string
  name: string
  role: Role
  active: boolean
  lastLogin: string
}
