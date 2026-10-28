import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiRequest, ApiError } from './http'
import type { ApiResponse } from './types'

// 해결 메모 API — 이슈 #153 제안 형식(contracts/api.md에는 아직 없음, 백엔드 합의 전까지 MSW 목).
// 응답 필드는 resolution_notes 테이블 컬럼 + 작성자 표시 이름(author_name, 제안).
export const NOTE_MAX_LENGTH = 1000

export interface NoteInput {
  root_cause: string
  action_taken: string
  result: string
}

export interface ResolutionNote extends NoteInput {
  id: number
  incident_id: number
  author_user_id: number
  author_name: string
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
