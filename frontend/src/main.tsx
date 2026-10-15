import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, HashRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AssistantProvider } from './state/AssistantProvider'
import { AuthProvider } from './state/AuthProvider'
import { PrefsProvider } from './state/PrefsProvider'
import './styles/tokens.css'
import './styles/global.css'

// 정적 파일로만 호스팅하는 미리보기(Artifact)에서는 해시 라우팅을 쓴다. 평소 개발·배포는 BrowserRouter.
const Router = import.meta.env.VITE_ROUTER === 'hash' ? HashRouter : BrowserRouter

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Router>
        <AuthProvider>
          <PrefsProvider>
            <AssistantProvider>
              <App />
            </AssistantProvider>
          </PrefsProvider>
        </AuthProvider>
      </Router>
    </QueryClientProvider>
  </StrictMode>,
)
