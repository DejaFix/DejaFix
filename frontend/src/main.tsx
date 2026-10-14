import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AssistantProvider } from './state/AssistantProvider'
import { AuthProvider } from './state/AuthProvider'
import { PrefsProvider } from './state/PrefsProvider'
import './styles/tokens.css'
import './styles/global.css'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <PrefsProvider>
            <AssistantProvider>
              <App />
            </AssistantProvider>
          </PrefsProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
