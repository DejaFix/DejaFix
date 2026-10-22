# common-frontend — 프론트엔드 공용 템플릿 (DejaFix 기준)

> 위치: DejaFix 저장소 `docs/common-frontend/`. 다음 프로젝트용 `common-frontend` 저장소를 만들면 이 폴더를 그대로 옮긴다(`templates/` 하위 유지, 코드 스냅샷은 그 저장소의 `snapshot/frontend/`에 둔다).
> 출처: DejaFix `frontend/` (`dev` 07d1db7, 2026-10-20 기준). React 19 + TypeScript + Vite 관리형 대시보드.
> 목적: 다음 프로젝트가 **디자인 토큰·공용 컴포넌트·데이터 연동 패턴·작업 규칙**을 처음부터 다시 만들지 않고 가져다 쓰게 한다.
> 이 문서는 코드를 복사해 둔 것이 아니라 **어디에 무엇이 있고 무엇을 가져가면 되는지** 안내한다. 코드는 아래 "스냅샷"으로 따로 보관한다.

## 문서 지도

| 문서 | 내용 | 읽는 때 |
|---|---|---|
| [01-design-tokens](01-design-tokens.md) | 색·글꼴·간격·라이트/다크·레이아웃·반응형 | 화면 모양을 정할 때 |
| [02-components](02-components.md) | 컴포넌트 카탈로그, 공통 CSS 클래스, 페이지 목록 | 컴포넌트를 가져올 때 |
| [03-architecture-and-patterns](03-architecture-and-patterns.md) | 폴더 구조, 인증·API·폴링·SSE 채팅·MSW·프록시 | 데이터를 붙일 때 |
| [04-ui-trust-rules](04-ui-trust-rules.md) | 모르는 값·실패·읽기 전용 표시 규칙 | AI·모니터링 화면을 만들 때 |
| [05-working-with-claude](05-working-with-claude.md) | Claude Code에 일을 시키는 방법, 프롬프트 템플릿 | 새 세션을 시작할 때 |
| [06-demo-flow-and-copy](06-demo-flow-and-copy.md) | 원본의 구조 속 프론트 위치, 시연 5단계↔화면, UI 문구 사전, 이후 예정 화면, 발표용 캡처 | 화면 흐름·문구를 맞출 때 |
| [templates/CLAUDE.frontend.md](templates/CLAUDE.frontend.md) | 새 프로젝트 `frontend/CLAUDE.md` 시작본 | 프로젝트 시작할 때 |

## 원본 프로젝트 한눈에 (발표 자료 기준)

**DejaFix — 장애 대응 코파일럿 · Zabbix AI.** 운영 Zabbix를 **조회만** 하는 AI Agent가 장애 원인을 분석하고, 조치는 **미리보기까지만** 보여 주며, 근거가 없으면 "확인할 수 없음"으로 표시한다.
구조는 `화면 → Backend → AI Agent → Zabbix MCP → 운영 Zabbix`의 **한 방향**이고, 프론트는 Backend `/api`만 부른다(자세한 내용은 06 문서).

## 가져갈 것 / 바꿀 것 / 버릴 것

| 구분 | 항목 |
|---|---|
| **그대로 가져감** | `styles/tokens.css` 구조, `Icon`·`Collapsible`·`EChart`·`UserMenu`, `useThemeVersion`, `lib/http.ts`·`tokenStorage.ts`·`chat.ts`, 인증 Provider 패턴, `queries.ts`의 폴링·오류 패턴, Vite 프록시·nginx 설정 |
| **이름·내용만 바꿈** | `Layout`의 메뉴 배열, `Chips`의 라벨, `format.ts`의 라벨 표, MSW 핸들러·목 데이터, 팔레트(`theme.css`) |
| **패턴만 참고** | `FocusCard`, `IncidentParts`(근거·계획·메일 조각), `ConnectionStatus`·`TopStatus` — 도메인(장애 대응)에 묶여 있음 |
| **버림** | `Legacy*` 타입·`mock.ts`의 옛 목, `/cost`·`/compare` 목 화면, 중복된 `.nav-soon` 등 (03·01 문서의 "정리할 것") |

## 새 프로젝트에서 쓰는 순서

1. 저장소를 만들고 `snapshot/frontend/`를 `frontend/`로 복사한다 (`npm ci`).
2. `templates/CLAUDE.frontend.md`를 `frontend/CLAUDE.md`로 복사해 `<…>` 부분을 채운다.
3. `tokens.css`·`theme.css`의 팔레트를 새 브랜드 색으로 바꾼다 (01 문서).
4. `Layout.tsx`의 `nav` 배열과 `lib/types.ts`를 새 계약에 맞춘다. 화면은 `lib/queries.ts` 훅 위에 만든다.
5. 백엔드가 없으면 `mocks/handlers.ts`로 시작하고, 계약이 정해지면 `VITE_MSW=off`로 실제 API에 붙인다.

## 독립 프로젝트로 분리할 때 의존하는 것

DejaFix는 한 저장소에 mcp·agent·backend·frontend가 같이 있다. 프론트만 떼어 쓸 때 **밖에서 오는 것**은 다음 둘뿐이다.

- **API 계약**: 응답 봉투 `{ data, meta }` / 오류 `{ error: { code, message } }`, `Measured`(값이 숫자·단위·수집 시각·`unknown`을 가짐), 15초 폴링. 새 프로젝트도 이 봉투를 쓰면 `lib/http.ts`가 그대로 동작한다.
- **`/api` 프록시**: 브라우저 코드는 상대 경로 `/api`만 쓴다. 개발은 Vite 프록시, 운영은 nginx가 백엔드로 넘긴다.

## 스냅샷 만들기 (Claude Code에 시킬 것)

문서는 요약이므로 코드는 파일 그대로 복사해 두는 편이 정확하다. 새 Claude Code 세션에서 아래를 시킨다.

```
DejaFix 저장소의 frontend/ 를 common-frontend 저장소의 snapshot/frontend/ 로 복사해 줘.
- 제외: node_modules, dist, public/mockServiceWorker.js(재생성 가능), package-lock.json 은 포함
- 제외 화면: src/pages 의 Cost.tsx, ServerCompare.tsx (목 전용)
- 복사한 뒤 snapshot/SOURCE.md 에 원본 저장소 주소, 커밋 해시, 날짜를 적어 줘
- 코드는 고치지 마. 복사만 해.
- 끝나면 snapshot/frontend 에서 npm ci && npm run lint && npx tsc --noEmit && npm run build 를 돌려 결과를 보고해 줘.
```

## 노션 구성 (제안)

```
프론트엔드 공용 템플릿 (상위 페이지)
├─ 개요·가져가는 법        ← README
├─ 디자인 토큰             ← 01
├─ 컴포넌트 카탈로그        ← 02
├─ 아키텍처·패턴           ← 03
├─ UI 신뢰 규칙            ← 04
└─ Claude Code로 일하기    ← 05 + 프롬프트 템플릿
```

각 `.md` 파일을 노션의 "가져오기 → Markdown"으로 넣으면 표와 코드 블록이 유지된다. 파일이 바뀌면 GitHub이 원본이고 노션은 사본이다.
