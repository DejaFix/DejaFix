import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AppRouter } from './AppRouter'
import { AssistantProvider } from './state/AssistantProvider'
import { AuthProvider } from './state/AuthProvider'
import { PrefsProvider } from './state/PrefsProvider'
import './styles/tokens.css'
import './styles/global.css'
import './styles/theme.css'
import './styles/shell.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } },
})

// 개발 서버에서만 MSW로 /api/auth/*를 목 처리한다(나머지 요청은 그대로 통과). VITE_MSW=off면 끈다.
async function enableMocking() {
  if (!import.meta.env.DEV || import.meta.env.VITE_MSW === 'off') return
  const { worker } = await import('./mocks/browser')
  await worker.start({ onUnhandledFrame: 'bypass' })
}

enableMocking().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <AppRouter>
          <AuthProvider>
            <PrefsProvider>
              <AssistantProvider>
                <App />
              </AssistantProvider>
            </PrefsProvider>
          </AuthProvider>
        </AppRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
})
