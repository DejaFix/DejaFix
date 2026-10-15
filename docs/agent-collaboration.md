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
