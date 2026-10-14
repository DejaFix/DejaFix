import type {
  AlertItem, BaselineItem, CrossServerGroup, DiskForecast, Incident, Plan, Report, Severity, Summary, TrendDay,
} from './types'

// 목업 데이터. 백엔드 API가 준비되면 api.ts의 호출만 교체한다.
export const BASE_TIME_KST = '2026-10-14 14:39'

export const alerts: AlertItem[] = [
  { id: 'a1', name: 'High memory utilization (>95% for 5m)', host: 'app-web-03', project: 'web', severity: 'average', minutesOpen: 12, repeat24h: 12, group: 'new' },
  { id: 'a2', name: 'CPU privileged time is too high (over 30% for 5m)', host: 'db-win-01', project: 'db', severity: 'warning', minutesOpen: 180, repeat24h: 23, group: 'new' },
  { id: 'a3', name: 'Number of installed packages has changed', host: 'batch-02', project: 'batch', severity: 'warning', minutesOpen: 300, repeat24h: null, group: 'new' },
  { id: 'a4', name: 'nvme4n1: Disk read/write request responses are too high', host: 'ml-gpu-07', project: 'ml', severity: 'info', minutesOpen: 34, repeat24h: 4, group: 'new' },
]

export const oldAlerts: AlertItem[] = Array.from({ length: 6 }, (_, i) => ({
  id: `o${i + 1}`,
  name: ['FS [/var]: Space is low (used > 90%)', 'Swap usage is high', 'Zabbix agent is not available', 'Load average is too high', 'Operating system description has changed', 'High swap space usage (less than 20% free)'][i],
  host: ['app-web-01', 'app-web-02', 'batch-01', 'db-win-02', 'edge-04', 'ml-gpu-02'][i],
  project: ['web', 'web', 'batch', 'db', 'edge', 'ml'][i],
  severity: (['warning', 'average', 'high', 'average', 'info', 'warning'] as Severity[])[i],
  minutesOpen: 1440 * (2 + i * 4),
  repeat24h: null,
  group: 'old' as const,
}))

export const summary: Summary = {
  newOpen: 4, repeating: 3, longOpen: 48, diskFullSoon: 15, openTotal: 52, serverTotal: 1057, collectedAt: BASE_TIME_KST,
}

export const crossGroups: CrossServerGroup[] = [
  { id: 'g1', name: 'Operating system description has changed', serverCount: 7 },
  { id: 'g2', name: 'High memory utilization (>95% for 5m)', serverCount: 4 },
  { id: 'g3', name: 'High swap space usage (less than 20% free)', serverCount: 4 },
  { id: 'g4', name: 'FS [/data]: Space is critically low (used > 95%)', serverCount: 3 },
]

export const baselines: BaselineItem[] = [
  { host: 'db-win-01', metric: 'CPU', now: 100, baselineMin: 0, baselineMax: 5.5, unit: '%', sinceMinutes: 379 },
  { host: 'app-web-03', metric: 'CPU', now: 54.4, baselineMin: 25.2, baselineMax: 41.1, unit: '%', sinceMinutes: 379 },
  { host: 'app-web-01', metric: 'CPU', now: 53.4, baselineMin: 25.2, baselineMax: 41.1, unit: '%', sinceMinutes: 379 },
  { host: 'ml-gpu-07', metric: 'CPU', now: 51.9, baselineMin: 24.9, baselineMax: 40.6, unit: '%', sinceMinutes: 64 },
]

const diskRaw: [string, number | null][] = [
  ['batch-02', 3], ['app-web-03', 4], ['db-win-01', 6], ['ml-gpu-04', 7], ['app-web-02', 9], ['edge-04', 11], ['ml-gpu-07', 12],
  ['batch-01', 13], ['db-win-02', 19], ['app-web-01', 23], ['edge-01', 25], ['ml-gpu-02', 28], ['legacy-nas', null],
]
export const diskForecasts: DiskForecast[] = diskRaw.map(([host, daysLeft]) => ({ host, daysLeft }))

const days = ['10/01', '10/02', '10/03', '10/04', '10/05', '10/06', '10/07', '10/08', '10/09', '10/10', '10/11', '10/12', '10/13', '10/14']
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

export const incidents: Record<string, Incident> = {
  a1: {
    alert: alerts[0],
    summary: 'app-web-03의 메모리 사용률이 95%를 넘는 상태가 5분 이상 이어졌고, 최근 24시간 동안 12번 반복되었습니다.',
    impact: ['web-front (고객 주문 화면) 응답 지연 가능', '같은 서버군(web)의 app-web-01도 CPU가 평소보다 높음'],
    timeline: [
      { at: '14:27', text: '메모리 사용률 95% 초과, 알림 발생' },
      { at: '14:29', text: 'AI가 초동 분석을 시작하고 읽기 전용 검증을 실행' },
      { at: '14:31', text: '원인 후보 3개 중 1개 확인, 1개 반증, 1개 판단 불가' },
    ],
    candidates: [
      { id: 'c1', title: '애플리케이션 캐시 누수', verdict: 'confirmed', summary: 'java 프로세스의 메모리가 6시간 동안 선형으로 증가하고 있습니다.', reason: '프로세스 메모리 추이가 증가 패턴과 일치합니다.', checks: [
        { tool: 'zabbix.history', command: 'item=proc.mem[java] range=6h', result: '2.1GB → 6.4GB, 시간당 약 0.7GB 증가', ms: 212 },
        { tool: 'zabbix.host', command: 'host=app-web-03 metrics=memory,swap', result: '메모리 96%, 스왑 41% 사용', ms: 148 },
      ] },
      { id: 'c2', title: '배치 작업의 일시적 메모리 점유', verdict: 'refuted', summary: '배치 작업은 새벽 시간대에만 실행됩니다.', reason: '장애 시각(14:27)에 실행 중인 배치가 없어 후보에서 제외합니다.', checks: [
        { tool: 'zabbix.history', command: 'item=proc.num[batch] range=24h', result: '14:00~15:00 실행 이력 없음', ms: 175 },
      ] },
      { id: 'c3', title: '최근 배포로 인한 설정 변경', verdict: 'unknown', summary: '배포 이력을 조회할 수 없어 판단할 수 없습니다.', reason: '배포 시스템이 아직 연결되지 않았습니다. 추정하지 않고 확인할 수 없음으로 표시합니다.', checks: [] },
    ],
    planId: 'p1',
  },
  a2: {
    alert: alerts[1],
    summary: 'db-win-01의 CPU 권한 시간(privileged time)이 30%를 넘는 상태가 이어지고 있습니다. 평소 범위는 0~5.5%입니다.',
    impact: ['주문 DB 응답 지연 가능', '결제 API는 현재 확인된 영향이 없음'],
    timeline: [{ at: '11:39', text: 'CPU 권한 시간 30% 초과' }, { at: '14:20', text: '최근 24시간 23회 반복으로 분류' }],
    candidates: [
      { id: 'c1', title: '백신 실시간 검사 부하', verdict: 'unknown', summary: '검사 프로세스 정보를 수집하지 않아 판단할 수 없습니다.', reason: '필요한 항목이 수집 대상에 없습니다.', checks: [] },
      { id: 'c2', title: '디스크 I/O 대기 증가', verdict: 'refuted', summary: '디스크 응답 시간이 정상 범위입니다.', reason: 'I/O 지표가 기준 이하입니다.', checks: [{ tool: 'zabbix.history', command: 'item=disk.await range=3h', result: '평균 3ms, 최대 9ms', ms: 190 }] },
    ],
    planId: null,
  },
  a3: {
    alert: alerts[2],
    summary: 'batch-02에 설치된 패키지 수가 변경되었습니다. 정보성 변화일 가능성이 높습니다.',
    impact: ['확인된 서비스 영향 없음'],
    timeline: [{ at: '09:39', text: '설치 패키지 수 변경 감지' }],
    candidates: [{ id: 'c1', title: '정기 보안 업데이트', verdict: 'unknown', summary: '변경 이력 시스템과 연결되지 않아 확인할 수 없습니다.', reason: '변경 계획 시스템 연결 후 확인할 수 있습니다.', checks: [] }],
    planId: null,
  },
  a4: {
    alert: alerts[3],
    summary: 'ml-gpu-07의 nvme4n1 디스크 응답 시간이 20ms를 넘었습니다. 학습 작업 중 체크포인트 저장 시간과 겹칩니다.',
    impact: ['학습 작업 속도 저하 가능'],
    timeline: [{ at: '14:05', text: '디스크 응답 시간 20ms 초과' }, { at: '14:20', text: '체크포인트 저장 시각과 일치 확인' }],
    candidates: [
      { id: 'c1', title: '체크포인트 저장으로 인한 일시적 쓰기 폭주', verdict: 'confirmed', summary: '15분 간격으로 쓰기량이 급증합니다.', reason: '알림 시각과 쓰기량 급증 시각이 일치합니다.', checks: [{ tool: 'zabbix.history', command: 'item=vfs.dev.write range=2h', result: '15분마다 최대 1.8GB/s 쓰기', ms: 230 }] },
      { id: 'c2', title: 'SSD 수명 저하', verdict: 'unknown', summary: 'SMART 정보를 수집하지 않아 판단할 수 없습니다.', reason: '수집 항목에 없습니다.', checks: [] },
    ],
    planId: null,
  },
}

export const plans: Plan[] = [
  {
    id: 'p1', incidentId: 'a1', title: 'app-web-03 java 프로세스 점검 및 재시작 계획', status: 'draft', risk: 'medium', createdAt: '2026-10-14 14:33',
    impact: ['재시작 동안 약 20초간 이 서버로 가는 요청이 실패할 수 있음', '같은 서버군 app-web-01, 02가 트래픽을 분담', '남은 서버의 CPU가 평소보다 더 오를 수 있음'],
    steps: [
      { command: 'jcmd <pid> GC.heap_info', purpose: '재시작 전 힙 상태를 기록해 원인 분석 근거로 남김', rollback: '읽기 전용이라 되돌릴 필요 없음' },
      { command: 'systemctl restart app-web', purpose: '메모리를 회수하기 위해 서비스를 재시작', rollback: '실패 시 systemctl start app-web, 이전 버전 설정 유지' },
    ],
  },
  {
    id: 'p2', incidentId: 'a4', title: 'ml-gpu-07 체크포인트 저장 간격 조정 계획', status: 'reviewed', risk: 'low', createdAt: '2026-10-14 14:28',
    impact: ['학습 재현성에는 영향 없음', '저장 간격이 늘어나면 장애 시 복구 지점이 멀어짐'],
    steps: [{ command: 'train.yaml: checkpoint_interval 15m → 30m', purpose: '쓰기 폭주 빈도 감소', rollback: '값을 15m으로 되돌림' }],
  },
]

export const reports: Report[] = [
  {
    id: 'r1', incidentId: 'a4', title: 'ml-gpu-07 디스크 응답 지연 보고', status: 'draft', createdAt: '2026-10-14 14:40',
    sections: [
      { heading: '요약', body: '14:05부터 ml-gpu-07의 nvme4n1 디스크 응답 시간이 20ms를 넘었습니다. 학습 작업의 체크포인트 저장과 시각이 일치합니다.' },
      { heading: '영향', body: '학습 작업 속도가 일시적으로 저하되었을 수 있습니다. 서비스 장애로 이어진 정황은 확인되지 않았습니다.' },
      { heading: '확인할 수 없는 항목', body: 'SSD 수명(SMART) 정보는 수집되지 않아 확인할 수 없습니다.' },
      { heading: '권고', body: '체크포인트 저장 간격을 15분에서 30분으로 늘리는 변경 계획을 검토하세요(실행은 승인 후 담당자가 수행).' },
    ],
  },
]
