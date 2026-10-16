import { useEffect, useState } from 'react'

// 라이트/다크가 바뀌면 값이 바뀐다. 차트 옵션의 의존성에 넣어 색을 다시 읽게 한다.
export function useThemeVersion(): number {
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const bump = () => setVersion((n) => n + 1)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', bump)
    const mo = new MutationObserver(bump)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      mq.removeEventListener('change', bump)
      mo.disconnect()
    }
  }, [])
  return version
}
