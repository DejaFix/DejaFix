// MSW를 API 묶음별로 끄는 설정. frontend/.env.example 참고.
// - VITE_MSW=off                       → MSW 전부 끔(모든 /api가 Vite 프록시 → 로컬 백엔드)
// - VITE_MSW_PASSTHROUGH=auth,health   → 적힌 묶음만 실제 백엔드로 보내고 나머지는 목
// 실제 백엔드가 받는 요청에는 실제 JWT가 있어야 하므로, 다른 묶음을 통과시키면 auth도 자동으로 통과시킨다.
export const API_GROUPS = ['auth', 'health', 'dashboard', 'problems', 'incidents', 'chat'] as const
export type ApiGroup = (typeof API_GROUPS)[number]

function parse(raw: string | undefined): Set<ApiGroup> {
  const names = (raw ?? '')
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean)
  const groups = new Set<ApiGroup>()
  for (const name of names) {
    if (name === 'all') API_GROUPS.forEach((g) => groups.add(g))
    else if ((API_GROUPS as readonly string[]).includes(name)) groups.add(name as ApiGroup)
    else console.warn(`[msw] VITE_MSW_PASSTHROUGH: 모르는 묶음 "${name}" (가능: ${API_GROUPS.join(', ')}, all)`)
  }
  if (groups.size > 0 && !groups.has('auth')) {
    console.warn('[msw] 실제 백엔드는 목 토큰을 받지 않으므로 auth도 통과시킵니다')
    groups.add('auth')
  }
  return groups
}

/** 실제 백엔드로 통과시키는 묶음. 비어 있으면 전부 목이다. */
export const passthroughGroups: ReadonlySet<ApiGroup> = parse(import.meta.env.VITE_MSW_PASSTHROUGH)
