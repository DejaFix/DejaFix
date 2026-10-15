import type {
  LegacyAlertItem,
  BaselineItem,
  CostItem,
  CrossServerGroup,
  DeliveryLog,
  DiskForecast,
  LegacyIncident,
  NotificationRule,
  LegacyPlan,
  LegacyReport,
  ServerMetric,
  LegacySeverity,
  LegacySummary,
  TrendDay,
  UserAccount,
  ChatEvent,
  ChatReply,
  DashboardSummary,
  Health,
  Incident,
  IncidentDetail,
  Problem,
} from './types'

// 목업 데이터. 백엔드 API가 준비되면 api.ts의 호출만 교체한다.
// - legacy*: 지금 화면(목업)이 쓰는 옛 형식. 화면 이전이 끝나면 지운다.
// - 파일 맨 아래 "API 계약 형식" 구역: 새 타입(types.ts 1구역) 기준 목. 노션 요청서 3장 예시 JSON 기준.
// - 그 밖(crossGroups·baselines·diskForecasts·trend·heatmap·servers·costItems·notificationRules·deliveries·users): 범위 밖 화면용, 그대로 둔다.
export const BASE_TIME_KST = '2026-10-14 14:39'

/** @deprecated 옛 현황 홈 새 장애 목업. 새 코드는 `incidentList`·`problems`(#10·#6)를 쓴다. */
export const legacyAlerts: LegacyAlertItem[] = [
  {
    id: 'a1',
    name: 'High memory utilization (>95% for 5m)',
    host: 'app-web-03',
    project: 'web',
    severity: 'average',
    minutesOpen: 12,
    repeat24h: 12,
    group: 'new',
  },
  {
    id: 'a2',
    name: 'CPU privileged time is too high (over 30% for 5m)',
    host: 'db-win-01',
    project: 'db',
    severity: 'warning',
    minutesOpen: 180,
    repeat24h: 23,
    group: 'new',
  },
  {
    id: 'a3',
    name: 'Number of installed packages has changed',
    host: 'batch-02',
    project: 'batch',
    severity: 'warning',
    minutesOpen: 300,
    repeat24h: null,
    group: 'new',
  },
  {
    id: 'a4',
    name: 'nvme4n1: Disk read/write request responses are too high',
    host: 'ml-gpu-07',
    project: 'ml',
    severity: 'info',
    minutesOpen: 34,
    repeat24h: 4,
    group: 'new',
  },
]

/** @deprecated 옛 현황 홈 오래된 장애 목업. 새 코드는 `incidentList`(#10)를 쓴다. */
export const legacyOldAlerts: LegacyAlertItem[] = Array.from({ length: 6 }, (_, i) => ({
  id: `o${i + 1}`,
  name: [
    'FS [/var]: Space is low (used > 90%)',
    'Swap usage is high',
    'Zabbix agent is not available',
    'Load average is too high',
    'Operating system description has changed',
    'High swap space usage (less than 20% free)',
  ][i],
  host: ['app-web-01', 'app-web-02', 'batch-01', 'db-win-02', 'edge-04', 'ml-gpu-02'][i],
  project: ['web', 'web', 'batch', 'db', 'edge', 'ml'][i],
  severity: (['warning', 'average', 'high', 'average', 'info', 'warning'] as LegacySeverity[])[i],
  minutesOpen: 1440 * (2 + i * 4),
  repeat24h: null,
  group: 'old' as const,
}))

/** @deprecated 옛 KPI 목업. 새 코드는 `dashboardSummary`(#5)를 쓴다. */
export const legacySummary: LegacySummary = {
  newOpen: 4,
  repeating: 3,
  longOpen: 48,
  diskFullSoon: 15,
  openTotal: 52,
  serverTotal: 1057,
  collectedAt: BASE_TIME_KST,
}

export const crossGroups: CrossServerGroup[] = [
  {
    id: 'g1',
    name: 'Operating system description has changed',
    serverCount: 7,
    hosts: ['app-web-01', 'app-web-02', 'app-web-03', 'batch-01', 'batch-02', 'edge-01', 'edge-04'],
  },
  {
    id: 'g2',
    name: 'High memory utilization (>95% for 5m)',
    serverCount: 4,
    hosts: ['app-web-01', 'app-web-02', 'app-web-03', 'batch-02'],
  },
  {
    id: 'g3',
    name: 'High swap space usage (less than 20% free)',
    serverCount: 4,
    hosts: ['app-web-03', 'db-win-01', 'ml-gpu-04', 'ml-gpu-07'],
  },
  {
    id: 'g4',
    name: 'FS [/data]: Space is critically low (used > 95%)',
    serverCount: 3,
    hosts: ['batch-02', 'ml-gpu-04', 'legacy-nas'],
  },
]

export const baselines: BaselineItem[] = [
  { host: 'db-win-01', metric: 'CPU', now: 100, baselineMin: 0, baselineMax: 5.5, unit: '%', sinceMinutes: 379 },
  { host: 'app-web-03', metric: 'CPU', now: 54.4, baselineMin: 25.2, baselineMax: 41.1, unit: '%', sinceMinutes: 379 },
  { host: 'app-web-01', metric: 'CPU', now: 53.4, baselineMin: 25.2, baselineMax: 41.1, unit: '%', sinceMinutes: 379 },
  { host: 'ml-gpu-07', metric: 'CPU', now: 51.9, baselineMin: 24.9, baselineMax: 40.6, unit: '%', sinceMinutes: 64 },
]

const diskRaw: [string, number | null][] = [
  ['batch-02', 3],
  ['app-web-03', 4],
  ['db-win-01', 6],
  ['ml-gpu-04', 7],
  ['app-web-02', 9],
  ['edge-04', 11],
  ['ml-gpu-07', 12],
  ['batch-01', 13],
  ['db-win-02', 19],
  ['app-web-01', 23],
  ['edge-01', 25],
  ['ml-gpu-02', 28],
  ['legacy-nas', null],
]
export const diskForecasts: DiskForecast[] = diskRaw.map(([host, daysLeft]) => ({ host, daysLeft }))

const days = [
  '10/01',
  '10/02',
  '10/03',
  '10/04',
  '10/05',
  '10/06',
  '10/07',
  '10/08',
  '10/09',
  '10/10',
  '10/11',
  '10/12',
  '10/13',
  '10/14',
]
const seed = [220, 410, 90, 140, 120, 330, 2400, 250, 160, 150, 140, 160, 200, 1250]
export const trend: TrendDay[] = days.map((label, i) => ({
  label,
  counts: {
    disaster: Math.round(seed[i] * 0.04),
    high: Math.round(seed[i] * 0.08),
    average: Math.round(seed[i] * 0.2),
    warning: Math.round(seed[i] * 0.38),
    info: Math.round(seed[i] * 0.3),
  },
}))

// 프로젝트 × 시간(0~23시) 히트맵. 난수 대신 고정 수식으로 만든다.
export const heatProjects = ['web', 'db', 'batch', 'ml', 'edge', 'infra']
export const heatmap: [number, number, number][] = heatProjects.flatMap((_, y) =>
  Array.from({ length: 24 }, (_, x) => {
    const v = Math.max(0, Math.round(((x * 7 + y * 13) % 11) * (y === 0 ? 6 : 2) * (x > 8 && x < 18 ? 1.6 : 0.5) - 8))
    return [x, y, v] as [number, number, number]
  }),
)

/** @deprecated 옛 장애 상세 목업. 새 코드는 `incidentDetails`(#11)를 쓴다. */
export const legacyIncidents: Record<string, LegacyIncident> = {
  a1: {
    alert: legacyAlerts[0],
    summary: 'app-web-03의 메모리 사용률이 95%를 넘는 상태가 5분 이상 이어졌고, 최근 24시간 동안 12번 반복되었습니다.',
    impact: ['web-front (고객 주문 화면) 응답 지연 가능', '같은 서버군(web)의 app-web-01도 CPU가 평소보다 높음'],
    timeline: [
      { at: '14:27', text: '메모리 사용률 95% 초과, 알림 발생' },
      { at: '14:29', text: 'AI가 초동 분석을 시작하고 읽기 전용 검증을 실행' },
      { at: '14:31', text: '원인 후보 3개 중 1개 확인, 1개 반증, 1개 판단 불가' },
    ],
    candidates: [
      {
        id: 'c1',
        title: '애플리케이션 캐시 누수',
        verdict: 'confirmed',
        summary: 'java 프로세스의 메모리가 6시간 동안 선형으로 증가하고 있습니다.',
        reason: '프로세스 메모리 추이가 증가 패턴과 일치합니다.',
        checks: [
          {
            tool: 'zabbix.history',
            command: 'item=proc.mem[java] range=6h',
            result: '2.1GB → 6.4GB, 시간당 약 0.7GB 증가',
            ms: 212,
          },
          {
            tool: 'zabbix.host',
            command: 'host=app-web-03 metrics=memory,swap',
            result: '메모리 96%, 스왑 41% 사용',
            ms: 148,
          },
        ],
      },
      {
        id: 'c2',
        title: '배치 작업의 일시적 메모리 점유',
        verdict: 'refuted',
        summary: '배치 작업은 새벽 시간대에만 실행됩니다.',
        reason: '장애 시각(14:27)에 실행 중인 배치가 없어 후보에서 제외합니다.',
        checks: [
          {
            tool: 'zabbix.history',
            command: 'item=proc.num[batch] range=24h',
            result: '14:00~15:00 실행 이력 없음',
            ms: 175,
          },
        ],
      },
      {
        id: 'c3',
        title: '최근 배포로 인한 설정 변경',
        verdict: 'unknown',
        summary: '배포 이력을 조회할 수 없어 판단할 수 없습니다.',
        reason: '배포 시스템이 아직 연결되지 않았습니다. 추정하지 않고 확인할 수 없음으로 표시합니다.',
        checks: [],
      },
    ],
    planId: 'p1',
  },
  a2: {
    alert: legacyAlerts[1],
    summary:
      'db-win-01의 CPU 권한 시간(privileged time)이 30%를 넘는 상태가 이어지고 있습니다. 평소 범위는 0~5.5%입니다.',
    impact: ['주문 DB 응답 지연 가능', '결제 API는 현재 확인된 영향이 없음'],
    timeline: [
      { at: '11:39', text: 'CPU 권한 시간 30% 초과' },
      { at: '14:20', text: '최근 24시간 23회 반복으로 분류' },
    ],
    candidates: [
      {
        id: 'c1',
        title: '백신 실시간 검사 부하',
        verdict: 'unknown',
        summary: '검사 프로세스 정보를 수집하지 않아 판단할 수 없습니다.',
        reason: '필요한 항목이 수집 대상에 없습니다.',
        checks: [],
      },
      {
        id: 'c2',
        title: '디스크 I/O 대기 증가',
        verdict: 'refuted',
        summary: '디스크 응답 시간이 정상 범위입니다.',
        reason: 'I/O 지표가 기준 이하입니다.',
        checks: [
          { tool: 'zabbix.history', command: 'item=disk.await range=3h', result: '평균 3ms, 최대 9ms', ms: 190 },
        ],
      },
    ],
    planId: null,
  },
  a3: {
    alert: legacyAlerts[2],
    summary: 'batch-02에 설치된 패키지 수가 변경되었습니다. 정보성 변화일 가능성이 높습니다.',
    impact: ['확인된 서비스 영향 없음'],
    timeline: [{ at: '09:39', text: '설치 패키지 수 변경 감지' }],
    candidates: [
      {
        id: 'c1',
        title: '정기 보안 업데이트',
        verdict: 'unknown',
        summary: '변경 이력 시스템과 연결되지 않아 확인할 수 없습니다.',
        reason: '변경 계획 시스템 연결 후 확인할 수 있습니다.',
        checks: [],
      },
    ],
    planId: null,
  },
  a4: {
    alert: legacyAlerts[3],
    summary: 'ml-gpu-07의 nvme4n1 디스크 응답 시간이 20ms를 넘었습니다. 학습 작업 중 체크포인트 저장 시간과 겹칩니다.',
    impact: ['학습 작업 속도 저하 가능'],
    timeline: [
      { at: '14:05', text: '디스크 응답 시간 20ms 초과' },
      { at: '14:20', text: '체크포인트 저장 시각과 일치 확인' },
    ],
    candidates: [
      {
        id: 'c1',
        title: '체크포인트 저장으로 인한 일시적 쓰기 폭주',
        verdict: 'confirmed',
        summary: '15분 간격으로 쓰기량이 급증합니다.',
        reason: '알림 시각과 쓰기량 급증 시각이 일치합니다.',
        checks: [
          {
            tool: 'zabbix.history',
            command: 'item=vfs.dev.write range=2h',
            result: '15분마다 최대 1.8GB/s 쓰기',
            ms: 230,
          },
        ],
      },
      {
        id: 'c2',
        title: 'SSD 수명 저하',
        verdict: 'unknown',
        summary: 'SMART 정보를 수집하지 않아 판단할 수 없습니다.',
        reason: '수집 항목에 없습니다.',
        checks: [],
      },
    ],
    planId: null,
  },
}

/** @deprecated 옛 변경 계획 목업([선택] 화면 /plans). 계약 형식은 `incidentDetails`의 plan·steps. */
export const legacyPlans: LegacyPlan[] = [
  {
    id: 'p1',
    incidentId: 'a1',
    title: 'app-web-03 java 프로세스 점검 및 재시작 계획',
    status: 'draft',
    risk: 'medium',
    createdAt: '2026-10-14 14:33',
    impact: [
      '재시작 동안 약 20초간 이 서버로 가는 요청이 실패할 수 있음',
      '같은 서버군 app-web-01, 02가 트래픽을 분담',
      '남은 서버의 CPU가 평소보다 더 오를 수 있음',
    ],
    steps: [
      {
        command: 'jcmd <pid> GC.heap_info',
        purpose: '재시작 전 힙 상태를 기록해 원인 분석 근거로 남김',
        rollback: '읽기 전용이라 되돌릴 필요 없음',
      },
      {
        command: 'systemctl restart app-web',
        purpose: '메모리를 회수하기 위해 서비스를 재시작',
        rollback: '실패 시 systemctl start app-web, 이전 버전 설정 유지',
      },
    ],
  },
  {
    id: 'p2',
    incidentId: 'a4',
    title: 'ml-gpu-07 체크포인트 저장 간격 조정 계획',
    status: 'reviewed',
    risk: 'low',
    createdAt: '2026-10-14 14:28',
    impact: ['학습 재현성에는 영향 없음', '저장 간격이 늘어나면 장애 시 복구 지점이 멀어짐'],
    steps: [
      {
        command: 'train.yaml: checkpoint_interval 15m → 30m',
        purpose: '쓰기 폭주 빈도 감소',
        rollback: '값을 15m으로 되돌림',
      },
    ],
  },
]

/** @deprecated 옛 리포트 목업([선택] 화면 /reports). 계약 형식은 `incidentDetails`의 report. */
export const legacyReports: LegacyReport[] = [
  {
    id: 'r1',
    incidentId: 'a4',
    title: 'ml-gpu-07 디스크 응답 지연 보고',
    status: 'draft',
    createdAt: '2026-10-14 14:40',
    sections: [
      {
        heading: '요약',
        body: '14:05부터 ml-gpu-07의 nvme4n1 디스크 응답 시간이 20ms를 넘었습니다. 학습 작업의 체크포인트 저장과 시각이 일치합니다.',
      },
      {
        heading: '영향',
        body: '학습 작업 속도가 일시적으로 저하되었을 수 있습니다. 서비스 장애로 이어진 정황은 확인되지 않았습니다.',
      },
      { heading: '확인할 수 없는 항목', body: 'SSD 수명(SMART) 정보는 수집되지 않아 확인할 수 없습니다.' },
      {
        heading: '권고',
        body: '체크포인트 저장 간격을 15분에서 30분으로 늘리는 변경 계획을 검토하세요(실행은 승인 후 담당자가 수행).',
      },
    ],
  },
]

// ---------- 서버 비교 ----------
const serverRows: [
  string,
  string,
  number | null,
  number | null,
  number | null,
  number | null,
  number | null,
  number | null,
  number,
][] = [
  // host, project, cpu, cpuBaselineMax, mem, disk, swap, ioMs, openAlerts
  ['app-web-01', 'web', 53.4, 41.1, 78, 61, 22, 4, 2],
  ['app-web-02', 'web', 44.8, 41.1, 81, 58, 18, 3, 1],
  ['app-web-03', 'web', 54.4, 41.1, 96, 91, 41, 6, 3],
  ['db-win-01', 'db', 100, 5.5, 74, 83, 35, 9, 2],
  ['db-win-02', 'db', 12.3, 18, 71, 66, 9, 5, 1],
  ['batch-01', 'batch', 9.1, 30, 20, 72, 4, 3, 1],
  ['batch-02', 'batch', 22.5, 30, 94, 96, 15, 5, 3],
  ['ml-gpu-02', 'ml', 33.0, 40.6, 61, 75, 12, 11, 1],
  ['ml-gpu-04', 'ml', 47.2, 40.6, 69, 97, 38, 8, 2],
  ['ml-gpu-07', 'ml', 51.9, 40.6, 66, 82, 33, 24, 2],
  ['edge-01', 'edge', 6.0, 15, 33, 54, 2, 2, 1],
  ['edge-04', 'edge', 8.4, 15, 36, 78, 3, 2, 1],
  ['legacy-nas', 'infra', null, null, 58, 99, null, null, 3],
]
export const servers: ServerMetric[] = serverRows.map(
  ([host, project, cpu, cpuBaselineMax, memory, disk, swap, ioMs, openAlerts], i) => ({
    host,
    project,
    cpu,
    cpuBaselineMax,
    memory,
    disk,
    swap,
    ioMs,
    openAlerts,
    collectedAt: BASE_TIME_KST,
    cpuSeries:
      cpu === null
        ? Array(24).fill(null)
        : Array.from({ length: 24 }, (_, h) => {
            const wave = Math.sin((h + i) / 3.2) * 6 + (h > 8 && h < 19 ? 8 : 0)
            return Math.max(1, Math.min(100, Math.round((cpu * 0.7 + wave + ((h * 7 + i * 3) % 5)) * 10) / 10))
          }),
  }),
)

// ---------- 비용 절감 (단가는 목업) ----------
export const costItems: CostItem[] = [
  {
    id: 'c1',
    host: 'app-web-01',
    currentType: 'm5.2xlarge',
    avgCpu: 31,
    p95Cpu: 58,
    avgMemory: 52,
    recommendedType: 'm5.xlarge',
    currentMonthly: 410000,
    recommendedMonthly: 205000,
    risk: 'medium',
    note: '최대 사용률이 58%라 반으로 줄여도 여유가 있지만, 트래픽이 갑자기 늘면 CPU가 80%를 넘을 수 있습니다.',
    evidence: [
      {
        tool: 'aws.cloudwatch',
        command: 'metric=CPUUtilization stat=p95 period=30d',
        result: '평균 31%, p95 58%',
        ms: 340,
      },
      {
        tool: 'aws.pricing',
        command: 'type=m5.2xlarge→m5.xlarge',
        result: '월 410,000원 → 205,000원 (목업 단가)',
        ms: 120,
      },
    ],
  },
  {
    id: 'c2',
    host: 'app-web-02',
    currentType: 'm5.2xlarge',
    avgCpu: 14,
    p95Cpu: 31,
    avgMemory: 38,
    recommendedType: 'm5.xlarge',
    currentMonthly: 410000,
    recommendedMonthly: 205000,
    risk: 'low',
    note: '30일 동안 CPU 최대 31%, 메모리 최대 52%라 한 단계 줄여도 안전합니다.',
    evidence: [
      {
        tool: 'aws.cloudwatch',
        command: 'metric=CPUUtilization stat=p95 period=30d',
        result: '평균 14%, p95 31%',
        ms: 310,
      },
      {
        tool: 'aws.cloudwatch',
        command: 'metric=mem_used_percent stat=max period=30d',
        result: '평균 38%, 최대 52%',
        ms: 290,
      },
    ],
  },
  {
    id: 'c3',
    host: 'batch-01',
    currentType: 'c5.4xlarge',
    avgCpu: 9,
    p95Cpu: 41,
    avgMemory: 20,
    recommendedType: 'c5.2xlarge',
    currentMonthly: 520000,
    recommendedMonthly: 260000,
    risk: 'medium',
    note: '평소 사용률은 낮지만 새벽 배치 시간에 CPU가 최대 78%까지 오릅니다. 배치 소요 시간이 늘 수 있습니다.',
    evidence: [
      {
        tool: 'aws.cloudwatch',
        command: 'metric=CPUUtilization stat=max period=30d',
        result: '최대 78% (새벽 02~04시)',
        ms: 360,
      },
    ],
  },
  {
    id: 'c4',
    host: 'edge-01',
    currentType: 't3.large',
    avgCpu: 6,
    p95Cpu: 15,
    avgMemory: 33,
    recommendedType: 't3.medium',
    currentMonthly: 92000,
    recommendedMonthly: 46000,
    risk: 'low',
    note: 'CPU와 메모리 사용률이 모두 낮습니다.',
    evidence: [
      {
        tool: 'aws.cloudwatch',
        command: 'metric=CPUUtilization stat=p95 period=30d',
        result: '평균 6%, p95 15%',
        ms: 280,
      },
    ],
  },
  {
    id: 'c5',
    host: 'ml-gpu-04',
    currentType: 'g5.2xlarge',
    avgCpu: 47,
    p95Cpu: 88,
    avgMemory: 69,
    recommendedType: null,
    currentMonthly: 1180000,
    recommendedMonthly: null,
    risk: null,
    note: '권고 없음. GPU 사용률이 평균 83%로 높아 유형을 줄이면 학습 시간이 늘어납니다.',
    evidence: [{ tool: 'aws.cloudwatch', command: 'metric=gpu_utilization period=30d', result: '평균 83%', ms: 330 }],
  },
  {
    id: 'c6',
    host: 'db-win-02',
    currentType: 'r5.2xlarge',
    avgCpu: 18,
    p95Cpu: 44,
    avgMemory: 71,
    recommendedType: null,
    currentMonthly: 620000,
    recommendedMonthly: null,
    risk: null,
    note: '권고 없음. CPU는 낮지만 메모리 사용률이 71%라 한 단계 줄이면 부족해질 수 있습니다.',
    evidence: [{ tool: 'aws.cloudwatch', command: 'metric=mem_used_percent period=30d', result: '평균 71%', ms: 300 }],
  },
  {
    id: 'c7',
    host: 'legacy-nas',
    currentType: 'm5.large',
    avgCpu: null,
    p95Cpu: null,
    avgMemory: null,
    recommendedType: null,
    currentMonthly: 205000,
    recommendedMonthly: null,
    risk: null,
    note: '확인할 수 없음. 에이전트가 CPU·메모리 지표를 수집하지 않았습니다.',
    evidence: [],
  },
  {
    id: 'c8',
    host: 'ml-gpu-02',
    currentType: 'g5.xlarge',
    avgCpu: 33,
    p95Cpu: 62,
    avgMemory: 61,
    recommendedType: null,
    currentMonthly: 880000,
    recommendedMonthly: null,
    risk: null,
    note: '확인할 수 없음. GPU 사용률 지표가 수집되지 않아 판단할 수 없습니다.',
    evidence: [
      { tool: 'aws.cloudwatch', command: 'metric=gpu_utilization period=30d', result: '조회 결과 없음', ms: 180 },
    ],
  },
]

// ---------- 알림 ----------
export const notificationRules: NotificationRule[] = [
  {
    id: 'n1',
    name: '높음 이상 장애 즉시 알림',
    condition: '심각도 높음 이상이 새로 열릴 때',
    recipients: 'ops-team@example.com',
    enabled: true,
  },
  {
    id: 'n2',
    name: '디스크 고갈 임박',
    condition: '디스크가 7일 안에 가득 찰 것으로 예측될 때',
    recipients: 'infra@example.com',
    enabled: true,
  },
  {
    id: 'n3',
    name: '반복 알림 일일 요약',
    condition: '매일 09:00, 24시간 3회 이상 반복된 알림',
    recipients: 'ops-team@example.com',
    enabled: false,
  },
  {
    id: 'n4',
    name: '변경 계획 검토 요청',
    condition: '새 변경 계획이 작성될 때',
    recipients: 'reviewers@example.com',
    enabled: true,
  },
]

export const deliveries: DeliveryLog[] = [
  {
    id: 'd1',
    at: '2026-10-14 14:31',
    rule: '디스크 고갈 임박',
    recipient: 'infra@example.com',
    status: 'sent',
    detail: '발송 완료',
  },
  {
    id: 'd2',
    at: '2026-10-14 14:28',
    rule: '변경 계획 검토 요청',
    recipient: 'reviewers@example.com',
    status: 'sent',
    detail: '발송 완료',
  },
  {
    id: 'd3',
    at: '2026-10-14 14:05',
    rule: '높음 이상 장애 즉시 알림',
    recipient: 'ops-team@example.com',
    status: 'failed',
    detail: '메일 서버 연결 시간 초과. 5분 뒤 다시 시도합니다.',
  },
  {
    id: 'd4',
    at: '2026-10-14 14:10',
    rule: '높음 이상 장애 즉시 알림',
    recipient: 'ops-team@example.com',
    status: 'pending',
    detail: '재시도 대기 중',
  },
  {
    id: 'd5',
    at: '2026-10-14 09:00',
    rule: '반복 알림 일일 요약',
    recipient: 'ops-team@example.com',
    status: 'sent',
    detail: '발송 완료',
  },
]

// ---------- 관리자 ----------
export const users: UserAccount[] = [
  { id: 'byunghwan', name: '배병환', role: 'admin', active: true, lastLogin: '2026-10-14 14:20' },
  { id: 'jaehyun', name: '재현', role: 'operator', active: true, lastLogin: '2026-10-14 13:02' },
  { id: 'yejin', name: '예진', role: 'operator', active: true, lastLogin: '2026-10-13 18:40' },
  { id: 'junha', name: '준하', role: 'operator', active: true, lastLogin: '2026-10-13 17:55' },
  { id: 'taeyun', name: '태윤', role: 'viewer', active: true, lastLogin: '2026-10-12 11:10' },
  { id: 'guest01', name: '외부 검토자', role: 'viewer', active: false, lastLogin: '2026-09-30 10:05' },
]

/** @deprecated `legacyAlerts` 별칭. components/Layout.tsx가 import한다. */
export const alerts = legacyAlerts
/** @deprecated `legacyOldAlerts` 별칭. components/Layout.tsx가 import한다. */
export const oldAlerts = legacyOldAlerts

// ============================================================================
// API 계약 형식 목 — types.ts 1구역 기준. 노션 프론트 API 요청서 3장 예시 JSON을 옮기고,
// FR-FE-015가 요구하는 경우(unknown:true, fallback 리포트, A·B·C 단계, failed 메일, 리포트 없음)를 더했다.
// 동작 ID·아이템 키는 목 데이터(fixture)라서 쓴다. 화면 코드에는 쓰지 않는다(NFR-EXT-001).
// ============================================================================

// #4 GET /api/health
export const health: Health = {
  zabbix: 'ok',
  agent: 'ok',
  mcp_zabbix: 'ok',
  shared_db: 'ok',
  backend_db: 'ok',
  scheduler_last_ok: '2026-10-16T01:20:30Z',
}

/** 연결 상태 경고 배너 확인용(요청서 #4 예시 그대로). */
export const healthDegraded: Health = {
  zabbix: 'ok',
  agent: 'ok',
  mcp_zabbix: 'down',
  shared_db: 'waiting',
  backend_db: 'ok',
  scheduler_last_ok: '2026-10-16T01:20:30Z',
}

// #5 GET /api/dashboard/summary
export const dashboardSummary: DashboardSummary = {
  active_incidents: { value: 3, unit: '건', collected_at: '2026-10-16T01:20:30Z', unknown: false },
  high_incidents: { value: 2, unit: '건', collected_at: '2026-10-16T01:20:30Z', unknown: false },
  hosts: {
    ok: { value: 2, unit: '대', collected_at: '2026-10-16T01:20:35Z', unknown: false },
    total: { value: 3, unit: '대', collected_at: '2026-10-16T01:20:35Z', unknown: false },
    unknown: { value: 1, unit: '대', collected_at: '2026-10-16T01:20:35Z', unknown: false },
  },
  reports_today: { value: 2, unit: '건', collected_at: '2026-10-16T01:20:40Z', unknown: false },
  avg_analysis_sec: {
    value: null,
    unit: 's',
    collected_at: '2026-10-16T01:20:40Z',
    unknown: true,
    unknown_reason: 'NO_DATA',
  },
  llm_usage_today: null,
}

// #6 GET /api/problems
export const problems: Problem[] = [
  {
    eventid: '40230',
    name: 'High CPU utilization (over 85% for 1m)',
    severity: { level: 4, label: 'High' },
    clock: '2026-10-16T01:24:00Z',
    host: { id: '10585', name: 'LAB-PC-08' },
    tags: [{ tag: 'component', value: 'cpu' }],
    incident_id: 13,
  },
  {
    eventid: '40211',
    name: 'Disk space is critically low (used > 90%) on C:',
    severity: { level: 4, label: 'High' },
    clock: '2026-10-16T01:20:00Z',
    host: { id: '10584', name: 'LAB-PC-07' },
    tags: [{ tag: 'component', value: 'storage' }],
    incident_id: 12,
  },
  {
    eventid: '40219',
    name: 'High CPU utilization (over 90% for 5m)',
    severity: { level: 3, label: 'Average' },
    clock: '2026-10-16T01:21:10Z',
    host: { id: '10585', name: 'LAB-PC-08' },
    tags: [],
    incident_id: null, // 아직 DejaFix가 수집하지 않음("수집 대기")
  },
]

// #10 GET /api/incidents — 상세(#11)와 같은 객체를 쓰도록 하나씩 정의한다(함수 호출 없이 두어야 운영 번들에서 빠진다)
const incident13: Incident = {
  id: 13,
  source: 'zabbix',
  zabbix: { eventid: '40230', triggerid: '23520', hostid: '10585' },
  host: { id: '10585', name: 'LAB-PC-08' },
  title: 'High CPU utilization (over 85% for 1m)',
  severity: { level: 4, label: 'High' },
  status: 'problem',
  started_at: '2026-10-16T01:24:00Z',
  resolved_at: null,
  tags: [{ tag: 'component', value: 'cpu' }],
  analysis: { status: 'fallback', report_id: 32, plan_id: 19 },
}

const incident12: Incident = {
  id: 12,
  source: 'zabbix',
  zabbix: { eventid: '40211', triggerid: '23512', hostid: '10584' },
  host: { id: '10584', name: 'LAB-PC-07' },
  title: 'Disk space is critically low (used > 90%) on C:',
  severity: { level: 4, label: 'High' },
  status: 'problem',
  started_at: '2026-10-16T01:20:00Z',
  resolved_at: null,
  tags: [{ tag: 'component', value: 'storage' }],
  analysis: { status: 'done', report_id: 31, plan_id: 18 },
}

const incident9: Incident = {
  id: 9,
  source: 'zabbix',
  zabbix: { eventid: '40102', triggerid: '23490', hostid: '10584' },
  host: { id: '10584', name: 'LAB-PC-07' },
  title: 'Operating system description has changed',
  severity: { level: 1, label: 'Information' },
  status: 'resolved',
  started_at: '2026-10-15T23:02:00Z',
  resolved_at: '2026-10-15T23:40:00Z',
  tags: [],
  analysis: { status: 'skipped', report_id: null, plan_id: null }, // ANALYZE_MIN_SEVERITY(2) 미만
}

// 호스트 보강 전(host·hostid null) — 화면은 UnknownValue로 그려야 한다(SAFE-10)
const incident14: Incident = {
  id: 14,
  source: 'zabbix',
  zabbix: { eventid: '40241', triggerid: '23525', hostid: null },
  host: { id: null, name: null },
  title: 'Zabbix agent is not available (for 3m)',
  severity: { level: 2, label: 'Warning' },
  status: 'problem',
  started_at: '2026-10-16T01:26:00Z',
  resolved_at: null,
  tags: [],
  analysis: { status: 'pending', report_id: null, plan_id: null },
}

// started_at 내림차순
export const incidentList: Incident[] = [incident14, incident13, incident12, incident9]

// #11 GET /api/incidents/{id}
export const incidentDetails: Record<number, IncidentDetail> = {
  // 호스트 보강 전 + 분석 대기: 리포트 없음(요청서 확인 요청 8)
  14: { incident: incident14, report: null, evidence: [], plan: null, steps: [], mail_logs: [] },
  // 요청서 #11 예시 그대로: LLM 리포트, A·B·C 단계, STALE 값, 메일 sent
  12: {
    incident: incident12,
    report: {
      id: 31,
      version: 1,
      kind: 'llm',
      summary: 'LAB-PC-07의 C: 드라이브 사용률이 96.1%로 임계값(90%)을 넘었습니다.',
      impact: {
        hosts: ['LAB-PC-07'],
        services: [],
        user_impact: '디스크가 가득 차면 실습 프로그램 저장이 실패할 수 있음',
        evidence_ids: ['ev_a1'],
      },
      causes: [
        {
          rank: 1,
          title: '임시 파일 누적',
          confidence: 'medium',
          reasoning: '최근 1시간 사용률이 꾸준히 증가했습니다.',
          evidence_ids: ['ev_a1', 'ev_a2'],
          verify: '임시 폴더 크기 확인',
        },
        {
          rank: 2,
          title: '백업 작업으로 인한 일시 증가',
          confidence: 'low',
          reasoning: '백업 작업 여부는 수집되지 않아 판단 근거가 부족합니다.',
          evidence_ids: [],
          verify: '백업 스케줄 확인',
        },
      ],
      facts: [
        {
          label: 'C: 사용률',
          value: 96.1,
          unit: '%',
          unknown_reason: null,
          evidence_ids: ['ev_a1'],
          collected_at: '2026-10-16T01:19:30Z',
        },
        {
          label: '메모리 사용률',
          value: null,
          unit: '%',
          unknown_reason: 'STALE',
          evidence_ids: ['ev_a3'],
          collected_at: '2026-10-16T00:40:00Z',
        },
      ],
      unknowns: [{ label: '백업 작업 여부', reason: 'NOT_COLLECTED' }],
      next_checks: ['임시 폴더 크기와 사용 중인 파일 확인'],
      created_at: '2026-10-16T01:20:52Z',
    },
    evidence: [
      {
        id: 'ev_a1',
        tool: 'zabbix_get_history',
        args: { itemid: '45123', time_from: '2026-10-16T00:20:00Z' },
        ok: true,
        duration_ms: 412,
        result_summary: '최근 1시간 C: 사용률 최대 96.1%',
        data_clock: '2026-10-16T01:19:30Z',
        called_at: '2026-10-16T01:20:41Z',
      },
      {
        id: 'ev_a2',
        tool: 'zabbix_list_items',
        args: { hostid: '10584', key_search: 'vfs.fs' },
        ok: true,
        duration_ms: 205,
        result_summary: 'C: 사용 중 공간 1시간 동안 4.2GB 증가',
        data_clock: '2026-10-16T01:19:30Z',
        called_at: '2026-10-16T01:20:42Z',
      },
      {
        id: 'ev_a3',
        tool: 'zabbix_list_items',
        args: { hostid: '10584', key_search: 'vm.memory' },
        ok: true,
        duration_ms: 188,
        result_summary: '메모리 값이 40분 전 이후 갱신 안 됨 (stale)',
        data_clock: '2026-10-16T00:40:00Z',
        called_at: '2026-10-16T01:20:43Z',
      },
    ],
    plan: {
      id: 18,
      title: 'LAB-PC-07 C: 드라이브 정리 계획',
      goal: 'C: 사용률을 90% 아래로',
      mode: 'preview',
      max_tier: 'C',
      assumptions: ['임시 폴더 파일은 업무 데이터가 아님'],
    },
    steps: [
      {
        seq: 1,
        action_id: 'check_disk_usage',
        title: '디스크 사용량 확인',
        target: 'LAB-PC-07 C:',
        command_preview: 'Get-PSDrive C',
        tier: 'A',
        rationale: '규칙: packs/it/actions.yaml check_disk_usage',
        precheck: null,
        expected_effect: '현재 사용량 확인',
        risk: '없음 (조회)',
        rollback: null,
        evidence_ids: ['ev_a1'],
      },
      {
        seq: 2,
        action_id: 'clean_temp_files',
        title: '임시 파일 정리',
        target: 'LAB-PC-07 %TEMP%',
        command_preview: 'Move-Item $env:TEMP\\* (Join-Path $env:TEMP ..\\dejafix-quarantine)',
        tier: 'B',
        rationale: '규칙: packs/it/actions.yaml clean_temp_files',
        precheck: '임시 폴더 크기와 사용 중인 파일 확인',
        expected_effect: '수 GB 확보 예상',
        risk: '사용 중인 파일 이동 시 프로그램 오류 가능',
        rollback: '격리 폴더의 파일을 원래 위치로 다시 이동',
        evidence_ids: ['ev_a1'],
      },
      {
        seq: 3,
        action_id: null,
        title: '서버 재부팅',
        target: 'LAB-PC-07',
        command_preview: 'Restart-Computer',
        tier: 'C',
        rationale: 'actions.yaml 미등록 동작 → C로 지정 (SAFE-06)',
        precheck: null,
        expected_effect: null,
        risk: '서비스 중단',
        rollback: null,
        evidence_ids: [],
      },
    ],
    mail_logs: [
      {
        id: 7,
        kind: 'incident_report',
        recipient: 'oncall@example.com',
        status: 'sent',
        attempts: 1,
        error: null,
        created_at: '2026-10-16T01:20:55Z',
        sent_at: '2026-10-16T01:20:58Z',
      },
    ],
  },

  // LLM 미연결 데모 기본 경로: fallback 리포트(원인 확인할 수 없음) + fallback 계획(A·B), 메일 failed
  13: {
    incident: incident13,
    report: {
      id: 32,
      version: 1,
      kind: 'fallback',
      summary:
        'LAB-PC-08의 CPU 사용률이 1분 평균 97.2%로 임계값(85%)을 넘었습니다. LLM이 연결되지 않아 수집한 사실만 정리했습니다.',
      impact: {
        hosts: ['LAB-PC-08'],
        services: [],
        user_impact: null,
        evidence_ids: ['ev_b1'],
      },
      causes: [],
      facts: [
        {
          label: 'CPU 사용률(1분 평균)',
          value: 97.2,
          unit: '%',
          unknown_reason: null,
          evidence_ids: ['ev_b2'],
          collected_at: '2026-10-16T01:24:30Z',
        },
        {
          label: '유지보수 여부',
          value: null,
          unit: null,
          unknown_reason: 'TOOL_ERROR',
          evidence_ids: ['ev_b3'],
          collected_at: null,
        },
      ],
      unknowns: [
        { label: '원인 후보', reason: 'NOT_COLLECTED' },
        { label: '같은 트리거 최근 7일 발생 횟수', reason: 'NOT_COLLECTED' },
      ],
      next_checks: ['부하 상위 프로세스 확인'],
      created_at: '2026-10-16T01:25:05Z',
    },
    evidence: [
      {
        id: 'ev_b1',
        tool: 'zabbix_get_problem',
        args: { eventid: '40230' },
        ok: true,
        duration_ms: 230,
        result_summary: '트리거 avg(system.cpu.util,1m)>85, 심각도 High',
        data_clock: '2026-10-16T01:24:00Z',
        called_at: '2026-10-16T01:24:58Z',
      },
      {
        id: 'ev_b2',
        tool: 'zabbix_get_history',
        args: { itemid: '45201', time_from: '2026-10-16T00:24:00Z' },
        ok: true,
        duration_ms: 398,
        result_summary: '최근 1시간 CPU 최대 99.1%, 1분 평균 97.2%',
        data_clock: '2026-10-16T01:24:30Z',
        called_at: '2026-10-16T01:24:59Z',
      },
      {
        id: 'ev_b3',
        tool: 'zabbix_get_host',
        args: { hostid: '10585' },
        ok: false,
        duration_ms: 5000,
        result_summary: 'ZABBIX_ERROR: 응답 시간 초과',
        data_clock: null,
        called_at: '2026-10-16T01:25:00Z',
      },
    ],
    plan: {
      id: 19,
      title: 'LAB-PC-08 CPU 과부하 확인 계획 (규칙 기반)',
      goal: null,
      mode: 'preview',
      max_tier: 'B',
      assumptions: [],
    },
    steps: [
      {
        seq: 1,
        action_id: 'check_top_process',
        title: '부하 상위 프로세스 확인',
        target: 'LAB-PC-08',
        command_preview: 'Get-Process | Sort-Object CPU -Descending | Select-Object -First 10',
        tier: 'A',
        rationale: '규칙: packs/it/actions.yaml fallback_plans.cpu',
        precheck: null,
        expected_effect: '부하 원인 프로세스 확인',
        risk: '없음 (조회)',
        rollback: null,
        evidence_ids: [],
      },
      {
        seq: 2,
        action_id: 'restart_service',
        title: '서비스 재시작',
        target: 'LAB-PC-08 <서비스 이름>',
        command_preview: 'Restart-Service -Name <서비스 이름>',
        tier: 'B',
        rationale: '규칙: packs/it/actions.yaml fallback_plans.cpu',
        precheck: '부하 상위 프로세스가 해당 서비스인지, 서비스 상태 확인 (Get-Service -Name <서비스 이름>)',
        expected_effect: 'CPU 사용률 하락',
        risk: '재시작 동안 해당 서비스 응답 없음',
        rollback: '서비스가 다시 뜨지 않으면 시작 (Start-Service -Name <서비스 이름>)',
        evidence_ids: [],
      },
    ],
    mail_logs: [
      {
        id: 8,
        kind: 'incident_report',
        recipient: 'oncall@example.com',
        status: 'failed',
        attempts: 3,
        error: 'SMTP 연결 시간 초과 (smtp.gmail.com:587)',
        created_at: '2026-10-16T01:25:10Z',
        sent_at: null,
      },
    ],
  },

  // 분석 대상이 아니라 리포트가 없는 장애(요청서 확인 요청 8 형태)
  9: {
    incident: incident9,
    report: null,
    evidence: [],
    plan: null,
    steps: [],
    mail_logs: [],
  },
}

// #18 POST /api/chat — SSE 이벤트 순서(요청서 #18 예시 그대로)
export const chatEvents: ChatEvent[] = [
  { event: 'meta', data: { conversation_id: 'c_7f3a', run_id: 'r_91b2', message_id: 101 } },
  {
    event: 'tool_call',
    data: { id: 'ev_c1', tool: 'zabbix_get_history', args: { itemid: '45123' }, started_at: '2026-10-16T01:25:02Z' },
  },
  {
    event: 'tool_result',
    data: {
      id: 'ev_c1',
      ok: true,
      duration_ms: 412,
      summary: '최근 1시간 C: 사용률 최대 96.1%',
      data_clock: '2026-10-16T01:24:30Z',
    },
  },
  { event: 'token', data: { text: '백업 작업 여부는 ' } },
  { event: 'token', data: { text: '수집되지 않아 확인할 수 없습니다.' } },
  {
    event: 'final',
    data: {
      message_id: 102,
      content: '백업 작업 여부는 수집되지 않아 확인할 수 없습니다. 최근 1시간 C: 사용률은 최대 96.1%입니다.',
      evidence_ids: ['ev_c1'],
      unknowns: [{ label: '백업 작업 여부', reason: 'NOT_COLLECTED' }],
    },
  },
]

/** LLM 미연결 규칙 기반 답변: meta → final만 온다. */
export const chatEventsRuleBased: ChatEvent[] = [
  { event: 'meta', data: { conversation_id: 'c_8a01', run_id: 'r_92c4', message_id: 103 } },
  {
    event: 'final',
    data: {
      message_id: 104,
      content: '이 서버의 백업 작업 정보는 수집 대상이 아니라 확인할 수 없습니다.',
      evidence_ids: [],
      unknowns: [{ label: '백업 작업 여부', reason: 'NOT_COLLECTED' }],
    },
  },
]

// #18 비스트리밍 대체 응답(탈출 규칙 1)
export const chatReply: ChatReply = {
  conversation_id: 'c_7f3a',
  message_id: 102,
  content: '백업 작업 여부는 수집되지 않아 확인할 수 없습니다. 최근 1시간 C: 사용률은 최대 96.1%입니다.',
  evidence_ids: ['ev_c1'],
  unknowns: [{ label: '백업 작업 여부', reason: 'NOT_COLLECTED' }],
  tool_calls: [
    {
      id: 'ev_c1',
      tool: 'zabbix_get_history',
      args: { itemid: '45123' },
      ok: true,
      duration_ms: 412,
      summary: '최근 1시간 C: 사용률 최대 96.1%',
      data_clock: '2026-10-16T01:24:30Z',
    },
  ],
}
