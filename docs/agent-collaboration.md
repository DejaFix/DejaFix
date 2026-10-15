# 에이전트 협업 — GitHub Issue를 "업무 요청 게시판"으로

> 상태: **초안(팀 승인 필요)** · 근거: 멘토 지시, 기획서 10장(역할·인수인계·결정 기록), `docs/work-order.md`, 루트 `CLAUDE.md` ③④⑦

각자의 Claude Code 세션(낮 세션·야간 루프)은 서로 직접 대화할 수 없다. 그래서 **다른 파트에 부탁할 일은 GitHub Issue로 요청하고, Issue에서 답한다.** 다른 파트 파일을 직접 고치지 않는다(루트 CLAUDE.md ③).

## 1. 누가 어떤 라벨을 보나
라벨은 **파트**에 붙는다. 사람은 로테이션(기획서 10-2)으로 바뀌어도 라벨은 그대로다.

| 라벨 | 파트 | 맡는 곳 | 현재 담당 |
|---|---|---|---|
| `to-infra` | 통합·프론트 연동 | 루트·`.claude/`·`.github/`, compose·Dockerfile, `docs/night/`, `frontend/src/lib`·`state`·`mocks` | 재현 |
| `to-frontend` | 프론트 화면 | `frontend/src/pages`·`components`·`styles` | 병환 |
| `to-backend` | 백엔드 | `backend/`, `libs/zabbix_ro/`, `contracts/api.md`·`incident.schema.json` | 준하 |
| `to-agent` | Agent·DB | `agent/`, `packs/it/actions.yaml`·`prompts/`, `scheduler/`, 메일 워커, `contracts/db-schema.sql`·`agent-api.md` | 예진 |
| `to-mcp` | Zabbix·MCP | `mcp-zabbix/`, `infra/zabbix/`, `infra/scripts/`, `packs/it/metrics.yaml`, `contracts/mcp-tools.md` | 재헌·태윤 |

상태 라벨: `accepted`(수락) · `counter`(대안 제안) · `in-progress`(작업 중) · `needs-human`(사람이 결정)

## 2. 흐름
```
요청 Issue 등록 ──► 받는 에이전트 확인 ──► 수락(accepted) ──► in-progress ──► 구현 PR("Closes #번호") ──► dev 머지 = Issue 자동 닫힘
                                   └──► 대안 제안(counter) ──► 요청자 응답 ──► 합의되면 수락으로
                                                                   └── 2번 주고받아도 안 되면 needs-human
```
1. **요청**: `업무 요청` 템플릿으로 Issue를 만들고 받는 파트 라벨(`to-*`) 하나를 붙인다. 제목은 `[요청 파트→받는 파트] 한 줄 요약`.
2. **확인**: 받는 에이전트는 작업을 시작할 때 자기 라벨의 열린 Issue부터 본다.
   - `gh issue list --label to-<파트> --state open`
3. **응답**(코멘트 1개 + 라벨)
   - 할 수 있으면 `accepted`, 언제·어느 PR로 할지 한 줄
   - 그대로는 어려우면 `counter`, 대안과 이유
4. **구현**: 시작하면 `in-progress`. PR 본문 "연결된 Issue"에 `Closes #번호`를 쓴다. dev가 기본 브랜치라 머지되면 Issue가 자동으로 닫힌다.
5. **기록**: 결정이 생기면(형식·책임·범위) `docs/decisions/NNN-제목.md`에 3줄(결정·이유·대안)로 남기고 Issue에 링크한다.

## 3. 계약이 바뀌는 요청
- 응답·요청 형식, 테이블, MCP 도구처럼 `contracts/`가 바뀌는 일은 **계약 PR이 먼저**다. 계약 PR은 2인 승인(계약 소유자 + 소비자 1명)이다.
- 구현 PR은 계약 PR이 머지된 뒤에 올린다(루트 CLAUDE.md ④).
- 계약을 바꾸지 않고 코드로 우회해 맞추지 않는다.

## 4. 사람에게 넘기는 경우 — `needs-human`
아래 중 하나면 에이전트는 진행을 멈추고 `needs-human` 라벨을 붙인다. 사람이 Issue 코멘트로 결정한다. 에이전트는 이 라벨을 떼거나 Issue를 닫지 않는다.
- 요청과 대안을 **2번 주고받아도 합의가 안 됨**
- **안전 규칙**(SAFE-01~18, 실행 경로·쓰기·근거 없는 값)에 걸림
- **범위**: [필수]가 아닌 기능, 새 화면·새 API, 일정이 밀리는 일
- **비용**: LLM 호출·외부 서비스 사용량이 늘어남
- **되돌릴 수 없는 일**: 데이터·DB 삭제, `main`·데모 동결 브랜치, 실메일 발송, 계정·권한·비밀값

## 5. 에이전트가 지킬 것
- 요청 하나 = Issue 하나. 하나에 여러 파트를 섞지 않는다.
- 코멘트는 짧게: **결론 한 줄 → 이유 → 다음 행동**.
- 비밀값·`.env` 내용은 Issue에 쓰지 않는다.
- 야간 루프도 Issue를 읽고 응답할 수 있다. 다만 `needs-human` Issue는 건너뛰고, 회차마다 작업은 하나만 한다(`docs/night/PROMPT.md`).
- 노션 현황표는 지금처럼 사람이 체크한다. Issue와 PR 링크는 산출물 칸에 붙인다.

## 6. 낮 운영 — 사람이 중계하지 않게
낮에도 각 파트 세션이 스스로 Issue를 확인하고, 통합 에이전트가 사람이 모르는 문제를 찾아 보고한다. `main` 머지·`needs-human` 결정·되돌릴 수 없는 일은 계속 사람 몫이다. dev 머지는 7장 자동 머지로 한다.

| 누가 | 무엇을 | 방법 |
|---|---|---|
| 각 파트 작업 세션 | 15분마다 자기 라벨 Issue 확인·응답 | 세션에서 `/loop 15m 내 라벨(to-<파트>) Issue 확인하고 응답해` — 응답 기준은 2·4장 |
| 통합 에이전트 (to-infra) | 60분마다 정찰 | `/loop 60m` 으로 `scout` 서브에이전트(`.claude/agents/scout.md`) 실행 → 빠진 요구사항·파트 간 불일치·담당 없는 작업·기한 위험을 `discovery` + `to-<파트>` Issue로 등록(중복 확인 후, 1회 최대 5개) |
| 통합 에이전트 | 하루 2번 보고 (12:30, 17:30) | `docs/reports/YYMMDD-HHMM.md` — ① 찾은 것(새 discovery Issue) ② 합의된 것(accepted·결정 기록) ③ 진행 중(in-progress·리뷰 대기 PR) ④ needs-human(사람이 결정할 것) ⑤ 다음 마감선까지 위험 |
| 사람 | 스탠드업에서 보고서와 `needs-human` 확인 | 결정은 Issue 코멘트 + `docs/decisions/` 3줄, 그다음 라벨을 뗀다 |

- `/loop`을 켠 세션은 작업 중에도 정해진 주기마다 Issue를 본다. 작업 흐름이 끊기지 않게 응답은 코멘트 1개로 끝내고, 수락한 요청은 지금 작업을 마친 뒤 시작한다.
- 보고서는 통합 에이전트의 PR에 함께 올리거나 `docs/reports-<날짜>` 브랜치로 dev에 PR한다(직접 push 금지).
- `discovery` Issue도 일반 요청과 같다. 받는 파트가 `accepted`·`counter`로 응답하고, 사실이 아니면 근거를 달아 사람에게 닫아 달라고 한다.

## 7. 자동 머지 — dev만
dev 머지는 에이전트가 한다. **`main` 머지는 사람만** 한다(dev → main은 데모·배포 시점, 팀장 승인, 루트 CLAUDE.md ⑦).

```
작성자 에이전트: 빌드·테스트 ──► dev로 PR ──► 자동 머지 예약(gh pr merge --auto --squash)
리뷰어 에이전트: PR 브랜치에서 빌드·테스트 ──► 문제 없으면 승인(gh pr review --approve) / 있으면 변경 요청
                                                        └──► 승인 충족 시 GitHub이 dev에 squash 머지
```
1. **작성자 에이전트**: PR을 올리기 전에 바꾼 영역의 린트·빌드·테스트를 직접 돌리고, 결과를 PR 본문 "테스트"에 붙인다. 그다음 `gh pr merge <번호> --auto --squash`로 예약한다.
2. **리뷰어 에이전트**: PR 브랜치를 받아 **직접** 같은 명령을 다시 돌린다. 작성자 결과를 믿고 넘기지 않는다. 통과하고 `plan-reviewer` 검사(SAFE 위반·계약 불일치·[이후] 침범·엔진 하드코딩)에 문제가 없을 때만 승인한다. 승인 본문에 돌린 명령과 결과를 한 줄씩 적는다.
3. **승인 충족 조건**: 작성자가 아닌 승인 1명 이상, 남은 변경 요청 없음, `needs-human` 라벨 없음. `contracts/`를 바꾸는 PR은 승인 2명(계약 소유자 + 소비자, 3장).
4. 변경 요청을 받으면 작성자가 고쳐 push하고, 변경을 요청한 리뷰어가 다시 확인해 승인한다.

| 영역 | 작성자·리뷰어가 돌릴 명령 |
|---|---|
| Python | `uv run ruff check .` · `uv run ruff format --check .` · `uv run pytest` · `uv run pytest -m safety_regression`(잘못 통과 0/N) |
| Frontend | `npm ci` · `npm run lint` · `npx tsc --noEmit` · `npm run build` |
| 문서·설정만 | 링크·표 확인. 하드코딩 검사(루트 CLAUDE.md ⑨) 0건 |

**강제 장치**
- `.claude/settings.json`: `gh pr review *`·`gh pr merge * --auto --squash*`만 허용하고, `--admin` 머지는 금지한다.
- `.claude/hooks/guard-merge.mjs`: 머지 명령 전에 PR을 조회해 **대상이 dev가 아니면**, 승인이 모자라거나 변경 요청·`needs-human`이 남아 있으면 막는다. PR 정보를 못 읽어도 막는다. 명령 위치(줄 처음, `;` `&` `|` `(` 뒤)에 있는 머지 명령만 검사하므로 커밋 메시지·PR 본문 속 문구는 막지 않는다.
- 승인은 GitHub 계정 단위다. 작성자 본인 계정의 승인은 세지 않는다. 그래서 리뷰어 에이전트는 **다른 팀원의 세션**이어야 한다.
- 지금 저장소에는 dev·main 브랜치 규칙이 없다(ruleset `develop`·`pr`가 `disabled`). 이 상태에서는 GitHub이 `--auto` 예약을 승인 전에도 바로 머지할 수 있어서, 위 훅이 먼저 막는다. 저장소 관리자가 ruleset을 켜서 dev에는 승인 1명, main에는 사람 승인과 직접 push 금지를 걸어야 GitHub 쪽에서도 막힌다.
- 에이전트는 머지를 되돌리지 않는다(revert·force push 금지). 잘못 머지되면 `needs-human` Issue로 올린다.
