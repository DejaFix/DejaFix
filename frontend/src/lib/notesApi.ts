import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, ApiError } from './http'
import type { ApiResponse } from './types'

// 해결 메모 API — 계약 PR #191(contracts/api.md #26·#27, Issue #153)의 형식. 백엔드(#197)가 머지되기 전까지 MSW 목.
export const NOTE_MAX_LENGTH = 1000

/** 입력(폼·POST 본문). 세 필드 모두 문자열이고 셋 다 비면 422 */
export interface NoteInput {
  root_cause: string
  action_taken: string
  result: string
}

/** 응답 1건. 서버가 앞뒤 공백을 자른 뒤 빈 값은 null로 저장하므로 필드가 null일 수 있다 */
export interface ResolutionNote {
  id: number
  incident_id: number
  root_cause: string | null
  action_taken: string | null
  result: string | null
  /** 작성자는 토큰에서만 채워진다. display_name이 없으면 서버가 username으로 대신한다 */
  author: { id: number; display_name: string }
  created_at: string // UTC ISO8601
}

const notesKey = (incidentId: number) => ['incidents', 'notes', incidentId] as const

/** GET /api/incidents/{id}/notes — viewer 이상 */
export function useResolutionNotes(incidentId: number) {
  return useQuery<ApiResponse<ResolutionNote[]>, ApiError>({
    queryKey: notesKey(incidentId),
    queryFn: ({ signal }) => apiRequest<ResolutionNote[]>(`/api/incidents/${incidentId}/notes`, { signal }),
    retry: false,
  })
}

/** POST /api/incidents/{id}/notes — operator 이상. 셋 다 비면 422 */
export function useAddResolutionNote(incidentId: number) {
  const queryClient = useQueryClient()
  return useMutation<ApiResponse<ResolutionNote>, ApiError, NoteInput>({
    mutationFn: (input) =>
      apiRequest<ResolutionNote>(`/api/incidents/${incidentId}/notes`, { method: 'POST', json: input }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notesKey(incidentId) }),
  })
}
