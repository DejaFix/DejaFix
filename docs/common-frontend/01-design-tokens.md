# 01. 디자인 토큰·레이아웃

위치: `frontend/src/styles/`. **색·크기는 전부 CSS 변수(토큰)로만 쓴다.** 컴포넌트 CSS에 색 값을 직접 쓰지 않는다.

## 1. 파일 구조와 적용 순서

`main.tsx`에서 이 순서로 import한다. 뒤 파일이 앞 파일을 덮어쓴다.

| 순서 | 파일 | 역할 |
|---|---|---|
| 1 | `tokens.css` | 기본 토큰(라이트) + 다크 토큰. **이름이 같은 토큰을 다시 정의**해서 테마를 바꾼다 |
| 2 | `global.css` | 공통 컴포넌트 클래스(`.card`·`.chip`·`.btn`…), 레이아웃, 장애 상세·AI 패널·현황 화면 |
| 3 | `theme.css` | 팔레트 덮어쓰기(인디고) + 각진 모양. **한 줄 import를 빼면 1번 모양으로 돌아간다** |
| 4 | `shell.css` | 어두운 사이드바(접기 포함)·헤더 구조 |

> 지금 **실제로 보이는 디자인은 3·4번이 덮어쓴 결과**(인디고 `#5b5bd6`, 어두운 사이드바, 모서리 0)다. 1번의 청록 팔레트는 기본값일 뿐이다.

## 2. 색 토큰 (라이트, theme.css 적용 후)

| 용도 | 토큰 | 값 |
|---|---|---|
| 배경 / 카드 / 카드 안쪽 | `--bg` / `--surface` / `--surface-2` | `#f6f6fb` / `#ffffff` / `#f1f1f9` |
| 글자 3단계 | `--text` / `--text-2` / `--text-3` | `#232345` / `#4a4a6e` / `#8a8aa8` |
| 선 | `--border` / `--border-strong` | `#e8e8f2` / `#d8d8e8` |
| 호버·트랙 | `--hover` / `--track` | `#eeeef8` / `#ebebf5` |
| 주 색 | `--primary` / `--primary-hover` / `--primary-soft` / `--on-primary` | `#5b5bd6` / `#4545b8` / `#ececfb` / `#fff` |
| 강조(주의) | `--accent` / `--accent-soft` | `#a8731a` / `#f6eedd` (tokens.css 값) |
| AI | `--ai` / `--ai-soft` | primary와 같음 |
| 사이드바 | `--side-bg` / `--side-text` / `--side-muted` / `--side-line` | `#1d1d3a` / `#e4e4f4` / `#9a9ac4` / `rgba(255,255,255,.1)` |
| 코드 블록 | `--code-bg` / `--code-fg` | `#232345` / `#f1f4f3` |

### 의미 색 (상태를 색으로 구분할 때)

| 의미 | 토큰 | 라이트 | 쓰는 곳 |
|---|---|---|---|
| 심각도 정보 / 경고 / 보통 / 높음 / 심각 | `--sev-info/warning/average/high/disaster` (+`-soft`) | `#3c6e9e` / `#a87a0a` / `#d06a1a` / `#cf3d34` / `#8f1d1d` | `.chip.info…disaster`, `.tile.sev-*`, `.urgent.sev-*` |
| 위험 낮음 / 보통 / 높음 | `--risk-low/medium/high` (+`-soft`) | `#2e9e6b` / `#a87a0a` / `#cf3d34` | `.chip.low/medium/riskhigh`, 성공(`.chip.green`) |
| 중립 칩 | `--chip-neutral-bg` | `#ebebf5` | `.chip.neutral` |
| 차트 계열 | `--series-1…4` | `#5b5bd6` / `#c9811f` / `#7fa3c7` / `#b1495a` | ECharts 색 |
| 히트맵 | `--heat-0…3` | 연한 회색 → 진한 빨강 | 히트맵 |

**칩 클래스 대응표** (`<span className="chip …">`): `info·warning·average·high·disaster`(심각도), `green`(성공·정상), `amber`(주의·fallback), `riskhigh`(실패·금지), `neutral`(대기·건너뜀·기본).

## 3. 글꼴·크기

- 글꼴: `Pretendard Variable`(index.html CDN) → 시스템 한글 글꼴. 코드는 `--mono`. 본문 15px / 줄간격 1.5.
- 크기 기준: 페이지 제목 28px·700, 카드 제목 17px·700, KPI 숫자 40px·700, 보조 글 13px, 칩 12px·700.
- 숫자는 `font-variant-numeric: tabular-nums`로 자릿수를 맞춘다.

## 4. 모양

| 항목 | 값 |
|---|---|
| 반경 | `--radius-lg/md/sm` = 18/12/8px (theme.css가 24/18/12로 바꾼 뒤 **0으로 덮음**) |
| 그림자 | `--shadow-sm`(카드), `--shadow-md`(팝업·패널) |
| 레이아웃 폭 | `--sidebar-w` 248px, `--collapsed-w` 64px, `--panel-w` 400px, `--topbar-h` 60px |

## 5. 라이트/다크

- 기본은 라이트. 다크는 **같은 토큰 이름을 다시 정의**한다: OS 설정(`prefers-color-scheme: dark`) 또는 `<html data-theme="dark|light">`로 수동 지정.
- 다크 토큰은 선택자(`:root:not([data-theme='light'])`, `:root[data-theme='dark']`)가 더 강해서 theme.css가 덮어쓰지 못한다.
- **차트(ECharts)** 는 CSS 변수를 못 읽으므로 `lib/colors.ts`의 `cssVar('--series-1')`로 현재 값을 읽고, `hooks/useThemeVersion.ts`를 옵션 의존성에 넣어 테마가 바뀌면 색을 다시 읽는다.

## 6. 레이아웃 골격

```
.shell (grid: 사이드바 | 본문)
├─ aside.sidebar     어두운 사이드바 (메뉴, 접기, 하단 시스템 상태)
└─ .main             본문. AI 패널이 열리면 .panel-open → margin-right: var(--panel-w)
   ├─ header.topbar  가장 급한 항목 배너 · 시간대 · 검색 · 사용자 · 알림 · AI 버튼
   ├─ nav.mobile-nav (900px 이하에서만)
   └─ <Outlet/>      페이지 (.page: padding 28px, max-width 1280px)
aside.assistant      우측 고정 패널 (translateX로 열림)
```

반응형: 1500px 이하(패널 열림 시 헤더 여백 축소) / 1280px 이하(현황 우측 레일 접힘) / 1100px 이하(KPI 4→2열, 2열 그리드 1열) / 980px 이하(요약 카드 1열) / **900px 이하(사이드바 숨김 + 모바일 메뉴)**.

## 7. 가져갈 때 정리할 것

- `.nav-soon`이 `global.css`(정의되지 않은 `--bg-muted`·`--text-muted` 변수로 대체값 사용)와 `shell.css`(정상)에 **두 번** 있다. 하나만 남긴다.
- `.evidence-head .dot`이 정의되지 않은 `--verdict-confirmed`를 쓴다. `--risk-low` 등으로 바꾼다.
- `shell.css`의 사이드바 상태 글자색(`#5fd79a`·`#f2c14e`·`#ff8a80`)은 토큰이 아니라 직접 값이다. 토큰으로 올린다.
- 모서리를 둥글게 하려면 `theme.css` 맨 아래의 `border-radius: 0 !important` 블록과 `:root{--radius-*:0}`을 지운다.
- 인라인 `style={{…}}`가 일부 남아 있다(AI 패널 정렬 등). 새 코드는 클래스로 쓴다.
