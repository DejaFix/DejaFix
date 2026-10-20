# frontend — <프로젝트 이름> (React + Vite + TypeScript)

먼저 읽을 것: 루트 `CLAUDE.md` → `<API 계약 문서 경로>` → `common-frontend` 의 01(토큰)·02(컴포넌트)·04(UI 신뢰 규칙).

## 소유 폴더
| 폴더 | 담당 |
|---|---|
| `src/pages`, `src/components`, `src/styles` | <화면 담당> |
| `src/lib`, `src/state`, `src/mocks`, `vite.config.ts`, `nginx.conf` | <연동 담당> |
다른 담당 폴더는 직접 고치지 않고 Issue(`to-<파트>`)로 요청한다.

## 원칙
- 화면은 **계약 타입 위에** 만든다. 계약과 다르면 코드로 우회하지 말고 "계약 변경 제안"으로 올린다.
- 색·크기는 토큰(`var(--…)`)만. 새 상태는 `Record<상태, {label, cls}>` 표로.
- 값이 없을 수 있는 곳은 항상 `Unknown`(확인할 수 없음 · 사유 · 수집 시각). 0·빈칸·`null` 글자 금지.
- 컴포넌트 파일은 컴포넌트만 export(`react-refresh` 린트). 상수·함수는 `lib/`.
- 범위 밖 화면은 코드를 건드리지 않고 "준비 중"으로 둔다. 자잘한 UI 수정은 `<백로그 파일>`에 적는다.

## 하지 않는 것
- 키·토큰을 `localStorage`·번들에 두기(JWT는 `sessionStorage`만)
- 백엔드 외 서버 직접 호출(항상 상대 경로 `/api`)
- <이 프로젝트 전용 금지 사항: 예) 실행 버튼, 확신도 퍼센트, 화면에서 분석 문장 계산>
- 새 화면·새 기능 선구현(요청된 범위만)

## 실행
- Node 22 LTS, npm만: `npm ci` → `npm run dev` (`http://localhost:5173`, 백엔드 없으면 MSW)
- 실제 API: `VITE_MSW=off` + 백엔드 기동 (`/api` 프록시는 Vite가 처리)
- 빌드: `npm run build`

## 머지 조건
- `npm run lint` · `npx tsc --noEmit` · `npm run build` 모두 통과
- 수동: DOM에 <금지 라벨> 요소 없음 / 토큰이 `localStorage`에 없음 / `null`이 모두 `Unknown` / 폴링 간격 15±2초
- PR ≤ 400줄, 브랜치 `feat/<영역>-<주제>`, 승인 1명 이상, **브라우저로 못 본 것은 PR 본문에 적는다**

## 작업 요청 형식 (Claude에게)
목표 / 범위(건드리지 말 것 포함) / 기준 문서 / 완료 기준(체크) / 검증 명령. 막히면 2번 시도 후 `[BLOCKED]`와 이유를 남긴다.
