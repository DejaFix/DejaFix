import type { ReactNode } from 'react'
import { BrowserRouter, HashRouter } from 'react-router-dom'

// 정적 파일로만 호스팅하는 미리보기(Artifact)에서는 해시 라우팅을 쓴다. 평소 개발·배포는 BrowserRouter.
export function AppRouter({ children }: { children: ReactNode }) {
  return import.meta.env.VITE_ROUTER === 'hash' ? (
    <HashRouter>{children}</HashRouter>
  ) : (
    <BrowserRouter>{children}</BrowserRouter>
  )
}
