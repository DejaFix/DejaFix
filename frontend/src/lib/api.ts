import { alerts, baselines, crossGroups, diskForecasts, heatmap, heatProjects, incidents, oldAlerts, plans, reports, summary, trend } from './mock'
import type { AssistantReply, EvidenceCall } from './types'

// 백엔드(BFF) API가 준비되면 이 파일의 함수 내부만 fetch로 바꾼다. 화면 코드는 그대로 둔다.
const wait = <T,>(value: T, ms = 220): Promise<T> => new Promise((resolve) => setTimeout(() => resolve(value), ms))

export const api = {
  summary: () => wait(summary),
  alerts: () => wait({ fresh: alerts, old: oldAlerts }),
  crossGroups: () => wait(crossGroups),
  baselines: () => wait(baselines),
  diskForecasts: () => wait(diskForecasts),
  trend: () => wait(trend),
  heatmap: () => wait({ projects: heatProjects, cells: heatmap }),
  incident: (id: string) => wait(incidents[id] ?? null),
  plans: () => wait(plans),
  plan: (id: string) => wait(plans.find((p) => p.id === id) ?? null),
  reports: () => wait(reports),
}

const tool = (name: string, command: string, result: string, ms: number): EvidenceCall => ({ tool: name, command, result, ms })

export async function askAssistant(question: string): Promise<AssistantReply> {
  const q = question.toLowerCase()
  await wait(null, 650)
  if (q.includes('확인') || q.includes('장애')) {
    return {
      text: '지금 새로 열린 장애는 4건입니다.\n1. app-web-03 메모리 95% 초과 (12분 전, 24시간 12회 반복)\n2. db-win-01 CPU 권한 시간 과다 (3시간 전)\n3. batch-02 설치 패키지 수 변경 (5시간 전)\n4. ml-gpu-07 디스크 응답 지연 (34분 전)\n우선 1번을 보시길 권합니다. 반복 횟수가 가장 많고 메모리 누수 가능성이 확인되었습니다.',
      evidence: [tool('zabbix.problems', 'severity>=info age<24h', '새 장애 4건, 오래된 장애 48건', 310), tool('zabbix.history', 'host=app-web-03 item=memory range=6h', '6시간 동안 선형 증가', 220)],
      unknowns: [],
    }
  }
  if (q.includes('cpu')) {
    return {
      text: '평소 범위를 크게 벗어난 서버는 db-win-01입니다(100%, 평소 0~5.5%). 나머지 3대는 평소보다 약 10~15%포인트 높은 수준입니다.',
      evidence: [tool('zabbix.trends', 'item=cpu.util range=30d', '서버별 평소 범위 계산', 420)],
      unknowns: [],
    }
  }
  if (q.includes('통신') || q.includes('끊')) {
    return {
      text: '통신이 끊긴 서버를 판단하려면 에이전트 연결 상태 데이터가 필요한데, 현재 수집되지 않아 확인할 수 없습니다.',
      evidence: [tool('zabbix.hosts', 'filter=availability', '가용성 항목 조회 결과 없음', 160)],
      unknowns: ['서버 통신 상태'],
    }
  }
  return {
    text: '이 질문에 답하려면 필요한 데이터가 조회되지 않았습니다. 추정해서 답하지 않고 확인할 수 없음으로 표시합니다. 다른 표현으로 물어보시거나 추천 질문을 이용해 주세요.',
    evidence: [tool('zabbix.search', `query="${question.slice(0, 24)}"`, '관련 항목 없음', 140)],
    unknowns: ['질문과 관련된 수집 항목'],
  }
}
