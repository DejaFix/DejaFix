import { setupWorker } from 'msw/browser'
import { handlers } from './handlers'
import { passthroughGroups } from './passthrough'

if (passthroughGroups.size > 0) {
  console.info(`[msw] 실제 백엔드로 통과: ${[...passthroughGroups].join(', ')} (나머지는 목)`)
}

export const worker = setupWorker(...handlers)
