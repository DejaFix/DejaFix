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
