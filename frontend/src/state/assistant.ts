import { createContext, useContext } from 'react'
import type { LegacyEvidenceCall } from '../lib/types'

export interface ChatMessage {
  id: number
  role: 'user' | 'ai'
  text: string
  evidence?: LegacyEvidenceCall[]
  unknowns?: string[]
}

export interface AssistantState {
  open: boolean
  setOpen: (open: boolean) => void
  messages: ChatMessage[]
  pending: boolean
  ask: (question: string) => void
  reset: () => void
}

export const AssistantContext = createContext<AssistantState | null>(null)

export function useAssistant(): AssistantState {
  const value = useContext(AssistantContext)
  if (!value) throw new Error('AssistantProvider 안에서만 사용할 수 있습니다')
  return value
}
