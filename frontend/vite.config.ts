import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// 개발 서버(5173)의 /api 요청을 로컬 백엔드(8000)로 넘긴다. 운영은 nginx가 같은 일을 한다(IF-INT-FE-001·002).
// 브라우저 코드는 항상 상대 경로 /api만 쓴다(절대 주소 환경 변수 금지). MSW가 켜진 API는 이 프록시까지 오지 않는다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        // 다른 포트로 띄운 격리 환경(scripts/dev-up.ps1 -BackendPort)은 DEV_API_TARGET 으로 바꾼다. 설정 시점에만 읽고 번들에는 들어가지 않는다.
        target: process.env.DEV_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          // 채팅 SSE(#18)가 모였다가 한 번에 오지 않게: 압축을 요청하지 않고, 응답 버퍼링 끔 헤더를 붙인다.
          proxy.on('proxyReq', (proxyReq) => proxyReq.removeHeader('accept-encoding'))
          proxy.on('proxyRes', (proxyRes) => {
            if (proxyRes.headers['content-type']?.startsWith('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache'
              proxyRes.headers['x-accel-buffering'] = 'no'
            }
          })
        },
      },
    },
  },
})
