# 03. 아키텍처·패턴

## 1. 스택 (`package.json`)

React 19 · TypeScript ~6 · Vite 8 · react-router-dom 7 · @tanstack/react-query 5 · echarts 6 · msw 3(개발) · ESLint 10 + typescript-eslint · Prettier 3. **Node 22 LTS, npm만**(`package-lock.json` 커밋, `npm ci`).
Prettier: 세미콜론 없음, 작은따옴표, 120자(`.prettierrc`).

## 2. 폴더

```
frontend/
├─ src/
│  ├─ main.tsx          부팅(Provider 순서)        ├─ pages/       화면 (라우트 1:1)
│  ├─ App.tsx           라우트 + RequireAuth       ├─ components/  공용 UI
│  ├─ AppRouter.tsx     Browser/Hash 라우터 선택   ├─ hooks/       useThemeVersion
│  ├─ lib/              API·타입·포맷·토큰 저장     ├─ state/       Context (auth·prefs·assistant)
│  ├─ mocks/            MSW 핸들러(개발 전용)      └─ styles/      tokens·global·theme·shell
├─ public/              favicon, 로고, mockServiceWorker.js
├─ nginx.conf · Dockerfile · vite.config.ts · eslint.config.js
├─ .env.example · .nvmrc(22) · .prettierrc · tsconfig.app.json
```

**소유 규칙(팀 합의)**: `pages`·`components`·`styles` = 화면 담당, `lib`·`state`·`mocks` = 연동 담당. 서로의 폴더는 직접 고치지 않고 이슈로 요청한다.

## 3. 부팅 순서 (`main.tsx`)

`QueryClientProvider`(기본 `staleTime 30s`, `retry 1`, `refetchOnWindowFocus false`) → `AppRouter` → `AuthProvider` → `PrefsProvider` → `AssistantProvider` → `App`.
개발 모드에서만 MSW를 켠다(`import.meta.env.DEV` 이고 `VITE_MSW !== 'off'`). `onUnhandledFrame: 'bypass'`라 목에 없는 요청은 실제 서버로 간다.

## 4. 인증

| 조각 | 파일 | 규칙 |
|---|---|---|
| 토큰 저장 | `lib/tokenStorage.ts` | **`sessionStorage`에만**(탭 닫으면 삭제). `localStorage` 금지. 브라우저 저장소는 이 파일에서만 다룬다. 저장 실패해도 동작 |
| 상태 | `state/auth.ts` + `state/AuthProvider.tsx` | `status: 'restoring' \| 'authenticated' \| 'anonymous'`, `login()`, `logout()`, `role`(없으면 가장 좁은 `viewer`) |
| 새로고침 복원 | `AuthProvider` | 저장된 토큰으로 `GET /api/auth/me`. 401이면 정리, **서버가 일시적으로 안 닿으면 세션 유지** |
| 라우트 가드 | `App.tsx`의 `RequireAuth` | `restoring`이면 아무것도 그리지 않음(깜빡임 방지) → 아니면 `/login`으로 |
| 401 전역 처리 | `lib/http.ts` | `handleUnauthorized()`가 토큰을 지우고 등록된 처리기(`setUnauthorizedHandler`)를 한 번만 부름 → 로그아웃 + `queryClient.clear()`(이전 사용자 화면 데이터 제거) |

> **Context 정의(`auth.ts`)와 Provider(`AuthProvider.tsx`)를 파일로 나눈다.** 한 파일에 컴포넌트와 상수·훅을 같이 export하면 react-refresh 린트가 실패한다. `assistant`·`prefs`도 같은 구조.

## 5. 데이터 패칭

- **`lib/http.ts`**: `apiRequest<T, M>(path, {json, query, auth, token, signal})` → `{data, meta}`, `apiData<T>`는 data만. 토큰을 `Authorization: Bearer`로 붙이고, 토큰이 없으면 요청을 보내지 않는다(로그아웃 직후 폴링 반복 방지). 실패는 `ApiError(status, code, message)`로 던진다(네트워크 오류는 `status 0, NETWORK_ERROR`).
- **`lib/queries.ts`**: 엔드포인트마다 훅 하나.
  - 전부 **15초 폴링**(`refetchInterval`), 4xx는 재시도하지 않고 네트워크·5xx만 1번 더.
  - `queryKeys`로 키를 한곳에서 관리.
  - **`hideDataOnError`**: 실시간 값(연결 상태·KPI·문제 목록)은 조회가 실패하는 동안 `data`를 숨긴다. react-query는 마지막 성공 값을 남기는데, 그걸 "지금 상태"처럼 보이면 안 되기 때문이다. 저장된 데이터(장애 목록·상세)는 유지하고 화면이 `isError`로 "갱신 실패"를 같이 보여 준다.
  - 상세 훅은 `id`가 양의 정수가 아니면 호출하지 않는다(`enabled`).
- **시간**: 서버는 UTC ISO8601, 화면에서 KST로 바꾼다(`kstShort`, 헤더 KST/UTC 토글은 `state/prefs`).

## 6. 채팅 스트림 (`lib/chat.ts` + `state/AssistantProvider.tsx`)

- **`EventSource`를 쓰지 않는다**(GET만 되고 `Authorization` 헤더를 못 붙임). `fetch` + `ReadableStream`으로 SSE를 직접 읽는다.
- SSE 프레임: 빈 줄이 경계, `event:` + `data:`(JSON). 이벤트 6종 `meta → (tool_call → tool_result)* → token* → final | error`.
- 응답 `Content-Type`이 JSON이면(비스트리밍 대체) 같은 이벤트 순서로 바꿔 넘긴다 → **화면 코드는 한 가지 경로**만 안다.
- `final`/`error` 없이 스트림이 끊기면 `AGENT_UNAVAILABLE`로 닫는다. 스트림 전 HTTP 오류는 `ApiError`.
- Provider: `token`을 이어 붙여 표시, `final`이 오면 확정, `tool_call/result`는 근거 행, `final.unknowns`는 "확인할 수 없음" 칩. 상세 화면(`/incidents/:id`)에서 열면 `context.incident_id`를 붙이고, 대화는 `conversation_id`로 이어 간다. 오류 코드 → 사용자 문구 표(`ERROR_TEXT`).

## 7. MSW (개발 전용 목)

- `mocks/handlers.ts`가 API 봉투 그대로 응답한다(`ok(data, meta)`, `error(status, code, message)`). 로그인은 토큰 `mock-jwt.<username>`.
- 시나리오: 주소에 `?scenario=zabbix_down`(또는 `VITE_MOCK_SCENARIO`)로 장애 상황을 재현.
- `VITE_MSW=off` + 백엔드 기동 → 실제 API. 이때 헤더의 "목업 데이터" 칩이 사라진다.
- 목 데이터에는 **`unknown:true`·fallback 리포트·실패한 근거·`failed` 메일** 같은 나쁜 경우를 일부러 넣어 둔다. 화면이 그 경우를 그리는지 확인하려는 것이다.

## 8. 개발 서버·배포

| 항목 | 내용 |
|---|---|
| Vite 프록시 | `/api` → `http://localhost:8000`(`DEV_API_TARGET`으로 변경). SSE가 뭉치지 않게 `accept-encoding`을 지우고 `cache-control: no-cache`·`x-accel-buffering: no`를 붙인다 |
| nginx | 정적 서빙, `/api/` → `backend:8000`(`proxy_buffering off`, `proxy_read_timeout 300s`), **`try_files $uri /index.html`**(SPA 새로고침·메일 링크 직접 진입) |
| 환경 변수 | `VITE_MSW=off`, `VITE_ROUTER=hash`(정적 호스팅 미리보기용 HashRouter). **절대 주소를 환경 변수로 두지 않는다**(항상 상대 경로 `/api`) |
| 외부 공개 | 프론트 nginx 하나만 공개, 나머지 서비스는 내부 |

## 9. 린트·타입 설정에서 알아 둘 것

- `eslint-plugin-react-refresh`: 컴포넌트 파일에서 컴포넌트만 export. 위반하면 `npm run lint` 실패(머지 조건).
- TypeScript(`tsconfig.app.json`): `noUnusedLocals`·`noUnusedParameters`(안 쓰는 변수·인자 오류), `verbatimModuleSyntax`(타입은 `import type`), `erasableSyntaxOnly`(enum 등 금지), `noFallthroughCasesInSwitch`.
- 머지 전 **`npm run lint` · `npx tsc --noEmit` · `npm run build`** 세 가지가 모두 통과해야 한다.

## 10. 정리할 것 (가져갈 때)

- `lib/types.ts`·`format.ts`·`mock.ts`에 **`Legacy*` 타입과 옛 목**이 남아 있다(옛 화면용). 새 프로젝트는 계약 타입만 두고 가져오지 않는다.
- 번들이 927kB(경고). 화면 단위 코드 분할(`React.lazy`)과 echarts 필요한 차트만 등록(이미 `EChart.tsx`는 그렇게 함)을 유지한다.
- `ConnectionStatus`의 칩 목록과 `TopStatus`의 `SystemList`가 같은 상태값을 두 번 정의한다. 하나로 합친다.
