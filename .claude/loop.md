# 낮 운영 루프 (15분)

> 기준: `docs/agent-collaboration.md` 2·4·7장, 루트 `CLAUDE.md`. 사용: 세션에서 `/loop 15m`
> 회차마다 아래 1→4를 순서대로 한 번 돈다. 하던 작업은 멈추지 않는다. 응답은 짧게 하고, 수락한 일은 지금 작업이 끝난 뒤 시작한다.

## 0. 준비
- `git fetch origin`
- 내 파트 라벨을 확인한다(`docs/agent-collaboration.md` 1장 표). 아래 `<파트>`는 그 라벨이다.

## 1. 내 라벨 Issue 응답
- `gh issue list --label to-<파트> --state open`
- `needs-human`이 붙은 Issue는 건너뛴다.
- 아직 응답하지 않은 Issue마다 코멘트 1개(**결론 한 줄 → 이유 → 다음 행동**) + 라벨 하나를 단다.
  - 할 수 있으면 `accepted`, 그대로는 어려우면 `counter`(대안과 이유), 시작하면 `in-progress`
- `contracts/`가 바뀌는 요청이면 계약 PR을 먼저 낸다(3장).

## 2. 내 PR — 변경 요청 반영·자동 머지 예약
- `gh pr list --author @me --base dev --state open`
- 변경 요청(`CHANGES_REQUESTED`)이 있는 PR
  1. 그 PR 브랜치에서 요청을 반영한다. 내 파트 폴더 밖은 고치지 않는다.
  2. 바꾼 영역의 린트·빌드·테스트를 직접 돌린다(7장 표).
  3. push하고 리뷰 코멘트에 "반영 내용 + 돌린 명령·결과"를 한 줄씩 답한다.
- 변경 요청이 없고 테스트가 통과한 PR은 `gh pr merge <번호> --auto --squash`로 자동 머지를 예약한다.
  - 훅(`guard-merge.mjs`)이 승인 부족으로 막으면 그대로 두고 다음 회차에 다시 본다. 우회하지 않는다.

## 3. 리뷰 요청된 PR — 직접 빌드·테스트 후 판정
- 리뷰어가 없는 새 dev PR(`gh pr list --base dev --state open --json number,author,reviewRequests,reviews,files`)은 바뀐 경로 기준으로 담당자를 리뷰어로 배정한다(`gh pr edit <번호> --add-reviewer <계정>`, 작성자 본인 제외, `contracts/`는 소유자+소비자 1명) — `frontend/src/pages`·`components`·`styles`→bxbae, `backend/`·`libs/zabbix_ro/`·`contracts/api.md`·`incident.schema.json`→manjo2828-blip, `agent/`·`scheduler/`·`packs/it/actions.yaml`·`prompts/`·`contracts/db-schema.sql`·`agent-api.md`→NYejin, `mcp-zabbix/`·`infra/zabbix/`·`infra/scripts/`·`packs/it/metrics.yaml`·`contracts/mcp-tools.md`→2taeyoon·areatmadm, 루트·`.claude/`·`.github/`·`docs/`·`frontend/src/lib`·`state`·`mocks`→JangJaehyeonn(본인 PR이면 부담당 manjo2828-blip)
- `gh pr list --search "review-requested:@me" --base dev --state open`
- 내가 작성한 PR은 리뷰하지 않는다. `contracts/` PR은 계약 소유자이거나 소비자 파트일 때만 승인한다.
- 하던 브랜치를 건드리지 않게 worktree에서 받는다.
  - `git worktree add .claude/worktrees/pr-<번호> origin/<head 브랜치>`
- 그 worktree에서 **직접** 7장 표의 명령을 돌린다. 작성자가 붙인 결과를 믿고 넘기지 않는다.
- `plan-reviewer` 서브에이전트로 SAFE 위반·계약 불일치·[이후] 침범·엔진 하드코딩을 확인한다.
- 판정
  - 모두 통과: `gh pr review <번호> --approve --body "<돌린 명령과 결과, 한 줄씩>"`
  - 문제 있음: `gh pr review <번호> --request-changes --body "<문제·재현·제안>"`
- 끝나면 `git worktree remove .claude/worktrees/pr-<번호>`

## 4. 합의가 안 되면 `needs-human`
아래 중 하나면 해당 Issue·PR에 `needs-human` 라벨을 붙이고 이유를 코멘트 1개로 남긴 뒤 그 건은 멈춘다(4장).
- 요청·대안 또는 변경 요청·반영을 **2번 주고받아도** 합의가 안 됨
- 안전 규칙(SAFE-01~18), 범위([필수] 밖), 비용 증가, 되돌릴 수 없는 일(`main`, 데이터 삭제, 실메일, 계정·비밀값)

## 하지 않는 것
- `main` 대상 머지, `--admin` 머지, force push, revert
- `needs-human` 라벨 떼기, Issue 닫기
- 다른 파트 폴더 파일 수정, `.env` 읽기·편집

## 회차 끝 보고
한 줄로: `Issue 응답 N · 내 PR 반영 N/예약 N · 리뷰 승인 N/변경 요청 N · needs-human N`
