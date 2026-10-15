# 야간 작업 루프 지시문 (기획서 9-3)

용어: 컨테이너 **Scheduler**(알람 폴링 배치)와 구분해 Claude Code `/loop 10m`으로 밤에 코드를 이어 짓는 절차를 **"야간 작업 루프"**라 부른다.

## 방식
- 파트별 학원 PC 1대에서 Claude Code 세션 1개를 **저장소 루트**에서 연다(루트·폴더 CLAUDE.md를 읽게).
- `/loop 10m` 뒤에 아래 지시문을 붙인다. `<파트>`·`<폴더>`·`<테스트 명령>`을 채운다.
- 작업 큐는 `docs/night/PLAN-<파트>.md`의 체크박스. 사람이 퇴근 전에 쓰고, 루프는 위에서부터 하나씩 처리한다.
- 리모트 컨트롤로 22:00·07:30 두 번 확인(각 파트 1명). 총괄 연동·인프라 담당.
- 권한 프롬프트는 `.claude/settings.json` 허용 목록으로 해결한다. **`--dangerously-skip-permissions`는 쓰지 않는다.**

## 지시문 (복사해서 사용)

```
너는 DejaFix <파트> 야간 작업 루프다. 매 회차 다음을 순서대로 한다.
1. 지금 진행 중인 작업(실행 중인 명령, 미완료 편집)이 있으면 아무것도 하지 말고 종료한다.
2. docs/night/PLAN-<파트>.md 에서 맨 위의 미완료 [ ] 항목 하나를 고른다. 없으면 docs/night/LOG-<파트>.md 에 "IDLE <시각>"만 쓰고 종료한다.
3. 루트 CLAUDE.md, <폴더>/CLAUDE.md, docs/mvp-checklist.md, contracts/ 를 기준으로 그 항목만 구현한다. 새 기능을 스스로 추가하지 않는다. 미결 값은 (TODO: 추후결정)으로 두고 임의로 채우지 않는다.
4. 테스트(<테스트 명령>)와 린트를 돌린다. 실패하면 최대 2번 고친다. 그래도 실패면 항목을 [BLOCKED]로 바꾸고 사유를 LOG에 쓴 뒤 다음 회차로 넘긴다.
5. 통과하면 night/<파트>-<MMDD> 브랜치(dev에서 분기)에 커밋 1개(Conventional Commits)를 만들고 push 한다. PR 대상은 dev다. PLAN 항목을 [x]로 바꾼다.
6. docs/night/LOG-<파트>.md 에 "시각 / 항목 / 결과 / 바뀐 파일 / 다음 사람이 알아야 할 것"을 한 줄 추가한다. 항목이 docs/work-order.md 의 T 번호를 끝낸 것이면 그 번호를 같은 줄에 적는다(노션 현황표 체크는 아침에 사람이 한다. 루프는 노션에 쓰지 않는다).
금지: main·dev 브랜치 직접 수정·push, contracts/·루트 CLAUDE.md·다른 파트 폴더 수정(필요하면 LOG에 "계약 변경 제안"으로만 기록),
.env 읽기·출력, 외부 서비스 쓰기(Slack·Notion·메일 실발송), 실 Zabbix 호출, 실 LLM 호출(LLM_FAKE=true 로 테스트),
장애 주입 스크립트 실행, rm -rf·git push --force·git reset --hard·docker system prune·DB 파일 삭제(테스트용 임시 DB 제외).
```

## 파트와 테스트 명령

| 파트 | 폴더 | 테스트 명령 | PLAN |
|---|---|---|---|
| frontend | `frontend/` | `npm run lint && npx tsc --noEmit && npm run build` | `PLAN-frontend.md` |
| frontend-api | `frontend/` | 위와 같음 | `PLAN-frontend-api.md` |
| backend | `backend/`, `libs/zabbix_ro/` | `uv run ruff check . && uv run ruff format --check . && uv run pytest` | `PLAN-backend.md` |
| scheduler-db | `scheduler/`, 메일 워커(`backend/` 안 메일 모듈만) | 위와 같음 | `PLAN-scheduler-db.md` |
| mcp-zabbix | `mcp-zabbix/` | 위와 같음 | `PLAN-mcp-zabbix.md` |
| agent | `agent/`, `packs/it/` | 위와 같음 + `uv run pytest -m safety_regression` | `PLAN-agent.md` |

## 운영 규칙
1. 아침 09:00: 각 파트가 LOG 확인 → `night/*` → **dev**로 PR → 사람이 리뷰 후 squash 머지. 루프가 만든 코드도 사람 리뷰 없이는 dev에 못 들어간다. 머지되면 LOG에 적힌 T 번호를 노션 「DejaFix 작업 진행 현황」 현황표에서 **`완료`로 체크**한다.
2. 루프가 3회 연속 BLOCKED면 리모트 확인 담당이 큐 순서를 바꾸거나 루프를 멈춘다.
3. 학원 PC가 재부팅되면 루프는 사라진다. 11-1 야간 가동 설정이 전제. 아침에 LOG 마지막 시각으로 중단 여부를 확인한다.
4. 10/15 야간(루프 2)은 **새 기능 금지**: 낮에 나온 버그 → 필수 SAFE 테스트 누락분 → `docker compose build` → README 실행 방법 → `docs/demo/` 대본 초안 순서.

## LOG 형식 (`LOG-<파트>.md`, 루프가 만든다)
```
| 시각(KST) | 항목 | 결과(done/BLOCKED/IDLE) | 바뀐 파일 | 다음 사람이 알아야 할 것 |
```
