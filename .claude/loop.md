# 낮 운영 루프 (15분)

> 기준: `docs/agent-collaboration.md` 2·4·7·8장, 루트 `CLAUDE.md`. 사용: 세션에서 `/loop 15m`
> 회차마다 아래 1→4를 **순서대로** 한 번 돈다. 앞 단계에서 할 일이 있으면 그것부터 한다. 응답은 짧게 하고, 수락한 일은 지금 작업이 끝난 뒤 시작한다.
> dev 머지는 GitHub이 한다: 필수 체크 `python`·`frontend`·`safety`(`.github/workflows/ci.yml`) 초록 + 작성자가 아닌 승인 1명(`contracts/`는 2명).

## 0. 준비
- `git fetch origin`
- 내 파트 라벨을 확인한다(`docs/agent-collaboration.md` 1장 표). 아래 `<파트>`는 그 라벨이다.

## 1. 남의 PR 리뷰 — 매 회차 가장 먼저, 최대 3개
- 대상: 작성자가 내가 아니고, 아직 승인이 없고, draft·`needs-human`이 아닌 열린 dev PR. 오래된 것부터 3개.
  - `gh pr list --base dev --state open --search "-author:@me review:none -label:needs-human draft:false sort:created-asc" --limit 3`
- 리뷰어가 없는 PR은 바뀐 경로 기준으로 담당자를 리뷰어로 붙인다(`gh pr edit <번호> --add-reviewer <계정>`, 작성자 본인 제외) — `frontend/src/pages`·`components`·`styles`→bxbae, `backend/`·`libs/zabbix_ro/`·`contracts/api.md`·`incident.schema.json`→manjo2828-blip, `agent/`·`scheduler/`·`packs/it/actions.yaml`·`prompts/`·`contracts/db-schema.sql`·`agent-api.md`→NYejin, `mcp-zabbix/`·`infra/zabbix/`·`infra/scripts/`·`packs/it/metrics.yaml`·`contracts/mcp-tools.md`→2taeyoon·areatmadm, 루트·`.claude/`·`.github/`·`docs/`·`frontend/src/lib`·`state`·`mocks`→JangJaehyeonn(본인 PR이면 부담당 manjo2828-blip)
- 확인할 것 4가지 (CI 결과는 `gh pr checks <번호>`, 코드는 `gh pr diff <번호>`. 필요하면 `git worktree add .claude/worktrees/pr-<번호> origin/<head 브랜치>`에서 직접 돌리고 끝나면 지운다)
  1. **계약 위반**: `contracts/`와 다른 요청·응답·테이블·도구 형식, 계약 PR 없이 바뀐 형식(④)
  2. **테스트 누락**: 바뀐 동작에 테스트가 없음, 필수 안전 테스트 8종이 빠짐
  3. **안전 규칙**: SAFE-02~16 (쓰기 메서드·실행 경로·근거 없는 값·키 노출 등). `plan-reviewer` 서브에이전트로 확인
  4. **하드코딩**: 엔진 코드에 IT 전용 키·동작 ID(루트 CLAUDE.md ⑨ 검사)
- 판정
  - 괜찮음: `gh pr review <번호> --approve --body "<근거 한 줄>"` (예: "계약·SAFE 변경 없음, 테스트 3건 추가, CI 초록")
  - 문제 있음: `gh pr review <번호> --request-changes --body "<파일:줄> — <문제> → <고칠 방향>"`
  - **판단이 어려움**(내 파트 밖 도메인, 계약 해석이 갈림): 승인하지 않는다. 그 파트 라벨을 PR에 붙이고(`gh pr edit <번호> --add-label to-<그 파트>`) 무엇이 애매한지 코멘트 1개만 남긴다.
- `contracts/` PR은 내가 계약 소유자이거나 소비자 파트일 때만 승인한다.

## 2. 내 PR — 올리자마자 자동 머지 예약, 막히면 고친다
- PR을 올리면 **바로** `gh pr merge <번호> --auto --squash`로 예약한다.
  - `guard-merge.mjs` 훅이 승인 부족으로 막으면 그대로 두고 다음 회차에 다시 예약한다. 우회하지 않는다.
- 회차마다 `gh pr list --author @me --base dev --state open --json number,headRefName,mergeable,reviewDecision,statusCheckRollup,autoMergeRequest`로 상태를 본다.
  - **CI 빨간색**: 실패 로그(`gh run view <run> --log-failed`)를 보고 고쳐서 push한다. 고치는 동안 `ci-failed` 라벨을 붙이고, 초록이 되면 뗀다.
  - **충돌**(`mergeable=CONFLICTING`): rebase하지 않는다. `git fetch origin` → `git merge origin/dev`(충돌 해결) → 바꾼 영역 테스트 → **일반 `git push`**. 해결하는 동안 `conflict` 라벨. force push는 쓰지 않는다(`.claude/settings.json` deny).
  - **스택 PR**(base가 다른 PR 브랜치): 부모 PR이 dev에 머지되면 같은 방식으로 `git fetch origin` → `git merge origin/dev` → 테스트 → 일반 `git push`, 그다음 `gh pr edit <번호> --base dev`로 base를 dev로 바꾸고 자동 머지를 다시 예약한다.
  - **변경 요청**(`CHANGES_REQUESTED`): 요청을 반영해 push하고, 리뷰 코멘트에 "반영 내용 + 돌린 명령·결과"를 한 줄씩 답한다. 내 파트 폴더 밖은 고치지 않는다.
  - push 뒤 예약이 풀렸으면 다시 예약한다.

## 3. 내 Issue — 내 라벨이고 담당자가 비어 있을 때만 잡는다
- `gh issue list --label to-<파트> --state open --search "no:assignee -label:needs-human"`
- 잡을 때: `gh issue edit <번호> --add-assignee @me` + 코멘트 1개(**결론 한 줄 → 이유 → 다음 행동**) + 라벨(`accepted` / `counter` / 시작하면 `in-progress`).
- 담당자가 이미 있는 Issue는 건드리지 않는다(다른 세션이 잡은 것).
- `contracts/`가 바뀌는 요청이면 계약 PR을 먼저 낸다(`docs/agent-collaboration.md` 3장).

## 4. 새 작업 — 1~3이 모두 비었을 때만
- `docs/work-order.md` 3장 레인에서 내 파트의 **다음 T 하나**를 고른다(앞 T가 끝났고, 열린 PR·Issue가 없는 것). [필수]가 남아 있으면 [선택]은 고르지 않는다(루트 CLAUDE.md ⑥).
- 작업 브랜치 → PR → 2단계 자동 머지 예약. 노션 현황표 체크는 사람에게 알린다.

## 5. 합의가 안 되면 `needs-human`
아래 중 하나면 해당 Issue·PR에 `needs-human` 라벨을 붙이고 이유를 코멘트 1개로 남긴 뒤 그 건은 멈춘다(`docs/agent-collaboration.md` 4장).
- 요청·대안 또는 변경 요청·반영을 **2번 주고받아도** 합의가 안 됨
- 안전 규칙(SAFE-01~18), 범위([필수] 밖), 비용 증가, 되돌릴 수 없는 일(`main`, 데이터 삭제, 실메일, 계정·비밀값)

## 하지 않는 것
- `main` 대상 머지, `--admin` 머지, force push(어느 브랜치든), rebase 후 push
- revert (통합 닥터의 revert **PR**만 예외 — 아래)
- `needs-human` 라벨 떼기, Issue 닫기
- 다른 파트 폴더 파일 수정, `.env` 읽기·편집

## 회차 끝 보고
한 줄로: `리뷰 승인 N/변경 요청 N/보류 N · 내 PR 예약 N/CI 수정 N/충돌 N/반영 N · Issue 잡음 N · 새 T <번호|없음> · needs-human N`

---

# 통합 닥터 (재현 루프 전용, to-infra)

> 통합 에이전트(재현) 세션에서만 돈다. 다른 파트 세션은 이 절을 실행하지 않는다. 위 1~5를 돈 뒤 같은 회차에 이어서 한다.

## D0. 실행 계정 확인 — 아니면 이 절 전체를 건너뛴다
- 회차마다 먼저 `gh api user --jq .login`으로 로그인 계정을 확인한다.
- 결과가 **`JangJaehyeonn`이 아니면** D1~D3을 실행하지 않고 회차를 끝낸다(닥터 보고 줄도 쓰지 않는다).
- 명령이 실패하거나 결과가 비어 있어도 건너뛴다(확인 못 하면 실행하지 않음).
- 담당자가 바뀌면(로테이션, 기획서 10-2) 이 계정 이름과 `docs/agent-collaboration.md` 1장 표를 같이 바꾼다.

## D1. 매 회차 — dev가 초록인지 직접 확인
- 전용 worktree에서 최신 dev를 받는다: `git worktree add .claude/worktrees/doctor origin/dev`(처음 한 번), 이후 `git -C .claude/worktrees/doctor fetch origin && git -C .claude/worktrees/doctor checkout --detach origin/dev`
- CI와 **같은 검사**를 돌린다(`.github/workflows/ci.yml`과 같은 명령):
  - python: `uv sync --locked` · `uv run ruff check .` · `uv run pytest -q`
  - frontend: `npm ci` · `npx tsc --noEmit -p tsconfig.app.json` · `npm run build` (frontend 폴더)
  - safety: `uv run pytest -m safety_regression -q` · 하드코딩 검사(ci.yml과 같은 grep) · `uv run --with jsonschema python .github/scripts/check_contracts.py`
- 참고로 dev push CI 결과도 본다: `gh run list --workflow ci --branch dev --event push --limit 10`

## D2. 깨졌으면 — 원인 커밋 revert PR + 원인 파트에 Issue
1. **원인 커밋 찾기**: 마지막 초록 커밋과 지금 사이를 `git bisect run <실패한 명령>`으로 좁힌다(dev는 squash 머지라 PR 1개 = 커밋 1개).
2. 같은 커밋에 열린 `auto-revert` PR이 이미 있으면 새로 만들지 않는다.
3. **revert PR**: `git switch -c fix/<영역>-revert-<sha7> origin/dev` → `git revert --no-edit <sha>` → 검사 재실행으로 초록 확인 → dev로 PR.
   - 제목 `revert: <원래 PR 제목> (#<원래 PR>) — dev CI 깨짐`, 라벨 `auto-revert`, 본문에 실패한 명령과 로그 요약(20줄 이내), 원래 PR 링크.
   - 일반 PR과 같이 승인 1명 + CI 초록으로 머지된다. `--admin`·직접 push로 되돌리지 않는다.
4. **원인 파트 Issue**: `.github/ISSUE_TEMPLATE/agent-request.md` 양식, 라벨 `to-<원인 파트>` + `auto-revert`. 실패한 명령·로그, revert PR 링크, "고친 뒤 원래 변경을 다시 PR" 요청.
5. 원인이 코드가 아닌 것 같으면(외부 서비스, 간헐 실패, 러너 문제) revert하지 않고 `needs-human` Issue로 올린다.

## D3. 아침 8:30 — 밤사이 요약 보고
- `docs/reports/YYMMDD-0830.md` (KST). 범위: 전날 18:00 ~ 오늘 08:30.
  1. **머지**: dev에 머지된 PR 목록(번호·제목·파트)
  2. **revert**: `auto-revert` PR·Issue와 상태
  3. **막힌 PR**: `ci-failed`·`conflict`·`CHANGES_REQUESTED`·승인 대기 6시간 이상(번호·막힌 이유·누구 차례)
  4. **needs-human**: 열린 Issue·PR과 사람이 결정할 것 한 줄씩
- `docs/reports-<YYMMDD>` 브랜치로 dev에 PR하고 자동 머지 예약(직접 push 금지).

## 닥터 회차 끝 보고
한 줄로: `dev <초록|빨강 sha7> · revert PR N · auto-revert Issue N · (08:30이면) 보고서 <경로>`
