import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { ApiError, apiRequest } from './http'
import type {
  ApiResponse,
  DashboardSummary,
  DashboardSummaryMeta,
  Health,
  HealthMeta,
  Incident,
  IncidentDetail,
  IncidentStatus,
  ListMeta,
  Problem,
  ProblemsMeta,
} from './types'

// 필수 API(#4·#5·#6·#10·#11)의 react-query 훅. 전부 15초마다 다시 조회한다(FR-FE-012).
// 반환값의 data는 응답 봉투 {data, meta} 그대로다. 예: const { data } = useHealth(); data?.data.zabbix
// 오류 중 data: react-query는 다시 조회가 실패해도 마지막 성공 값을 남긴다.
//  - Zabbix 실시간 값(#4·#5·#6)은 실패하는 동안 data를 undefined로 감춘다 → 화면은 error로 배너·UnknownValue를 그린다(SAFE-09).
//  - 저장된 장애(#10·#11)는 마지막 값을 유지한다. 화면은 isError면 "갱신 실패" 표시를 함께 보여 준다.
// 채팅(#18)은 SSE라 별도 PR에서 다룬다.

export const REFETCH_INTERVAL_MS = 15_000

// 4xx(401·403·404 등)는 다시 시도해도 같으므로 재시도하지 않는다. 네트워크 오류·5xx만 1번 더.
const retry = (failureCount: number, error: Error) =>
  !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 1

const polling = { refetchInterval: REFETCH_INTERVAL_MS, retry } as const

/** 조회가 실패하는 동안 지난 성공 값을 지금 상태처럼 보여 주지 않도록 data를 감춘다(SAFE-09, NFR-AVAIL-004). */
function hideDataOnError<T>(query: UseQueryResult<T, ApiError>): UseQueryResult<T, ApiError> {
  return query.isError ? ({ ...query, data: undefined } as UseQueryResult<T, ApiError>) : query
}

export const queryKeys = {
  health: ['health'] as const,
  dashboardSummary: ['dashboard', 'summary'] as const,
  problems: (params: ProblemsParams) => ['problems', params] as const,
  incidents: (params: IncidentsParams) => ['incidents', params] as const,
  incidentDetail: (id: number) => ['incidents', 'detail', id] as const,
}

/** #4 GET /api/health — 상단 연결 상태. 실패 중에는 data가 undefined(연결 상태를 '확인할 수 없음'으로) */
export function useHealth() {
  const query = useQuery<ApiResponse<Health, HealthMeta>, ApiError>({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => apiRequest<Health, HealthMeta>('/api/health', { signal }),
    ...polling,
  })
  return hideDataOnError(query)
}

/** #5 GET /api/dashboard/summary — 현황 홈 KPI 4종(값은 Measured). 실패 중에는 data가 undefined */
export function useDashboardSummary() {
  const query = useQuery<ApiResponse<DashboardSummary, DashboardSummaryMeta>, ApiError>({
    queryKey: queryKeys.dashboardSummary,
    queryFn: ({ signal }) => apiRequest<DashboardSummary, DashboardSummaryMeta>('/api/dashboard/summary', { signal }),
    ...polling,
  })
  return hideDataOnError(query)
}

export interface ProblemsParams {
  severity_min?: number
  hostid?: string
}

/** #6 GET /api/problems — Zabbix 실시간 문제. Zabbix가 끊기면 error.code 'ZABBIX_UNAVAILABLE'(503)이고 data는 undefined */
export function useProblems(params: ProblemsParams = {}) {
  const query = useQuery<ApiResponse<Problem[], ProblemsMeta>, ApiError>({
    queryKey: queryKeys.problems(params),
    queryFn: ({ signal }) => apiRequest<Problem[], ProblemsMeta>('/api/problems', { signal, query: { ...params } }),
    ...polling,
  })
  return hideDataOnError(query)
}

export interface IncidentsParams {
  status?: IncidentStatus
  severity_min?: number
  limit?: number
  cursor?: string
}

/** #10 GET /api/incidents — 수집된 장애 목록(started_at 내림차순). 다음 쪽은 meta.next_cursor */
export function useIncidents(params: IncidentsParams = {}) {
  return useQuery<ApiResponse<Incident[], ListMeta>, ApiError>({
    queryKey: queryKeys.incidents(params),
    queryFn: ({ signal }) => apiRequest<Incident[], ListMeta>('/api/incidents', { signal, query: { ...params } }),
    placeholderData: keepPreviousData,
    ...polling,
  })
}

/** #11 GET /api/incidents/{id} — 장애 상세. id가 숫자가 아니면 호출하지 않는다. 없는 id는 error.status 404 */
export function useIncidentDetail(id: number | string | undefined) {
  const numericId = typeof id === 'string' ? Number(id) : id
  const valid = numericId !== undefined && Number.isInteger(numericId) && numericId > 0
  return useQuery<ApiResponse<IncidentDetail>, ApiError>({
    queryKey: queryKeys.incidentDetail(valid ? numericId : -1),
    queryFn: ({ signal }) => apiRequest<IncidentDetail>(`/api/incidents/${numericId}`, { signal }),
    enabled: valid,
    ...polling,
  })
}
