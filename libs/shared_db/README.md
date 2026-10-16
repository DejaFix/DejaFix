# libs/shared_db — 공유 DB 스키마 적용·개발 시드

담당: DB·메일 담당 (부 Backend 담당). 기준 계약: `contracts/db-schema.sql`, `contracts/agent-api.md`.

| 경로 | 내용 | 상태 |
|---|---|---|
| `fixtures/seed_dev.sql` | 개발용 시드. 장애 6건으로 화면 분석 상태 6값과 요청서 #11 응답 모양을 전부 만든다 | 있음 |
| `shared_db/__init__.py` | `open_db(path, "shared"|"backend")`: 연결 PRAGMA + 구역별 멱등 적용 (T35). `connect(..., uri=True)`는 Backend의 읽기 전용 ATTACH용. `load_dev_seed()`는 개발 시드 | 있음 |

## 시드 넣기 (개발 PC에서만)

`contracts/db-schema.sql`과 `seed_dev.sql`은 둘 다 `-- @db shared`, `-- @db backend` 구역으로 나뉜다. 구역을 **해당 DB에만** 실행해야 한다. 아래 명령은 저장소 루트에서 실행하고, 기본으로 `./data/`에 두 파일을 만든다.

```powershell
uv run --no-project --python 3.12 python -I -c "
import re, sqlite3, pathlib
out = pathlib.Path('data'); out.mkdir(exist_ok=True)
def sections(p):
    parts = re.split(r'^-- @db (\w+)\s*$', pathlib.Path(p).read_text(encoding='utf-8'), flags=re.M)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
schema, seed = sections('contracts/db-schema.sql'), sections('libs/shared_db/fixtures/seed_dev.sql')
for db in ('shared', 'backend'):
    c = sqlite3.connect(out / f'{db}.db')
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA foreign_keys=ON')
    c.executescript(schema[db]); c.executescript(seed[db]); c.commit(); c.close()
print('ok')
"
```

- 여러 번 실행해도 행이 늘지 않는다(전부 `INSERT OR IGNORE`). 처음부터 다시 하려면 `data/*.db*`를 지운다.
- `*.db`·`*.db-wal`·`*.db-shm`은 `.gitignore` 대상이라 커밋되지 않는다.
- `users`는 시드하지 않는다. Backend가 기동 시 `.env`의 `DEMO_*_PASSWORD`로 `admin`·`oncall`을 만든다.
- Backend에서 쓸 때는 `.env`의 `SHARED_DB_PATH`·`BACKEND_DB_PATH`를 이 파일로 가리키고, `backend.db`를 `uri=True`로 연 뒤 `shared.db`를 `?mode=ro`로 ATTACH 한다.

## 시드가 만드는 상태

| 장애 id | 내용 | 화면 `analysis.status` | 확인할 것 |
|---|---|---|---|
| 1 | CPU High, llm 리포트 | `done` | 원인 2개(근거 없는 2순위는 low), STALE 값, NOT_COLLECTED 2건, 계획 A·B·C, 메일 sent |
| 2 | 메모리 Average, fallback 리포트 | `fallback` | fallback 라벨, 실패한 근거(ok=0), A 단계만, 메일 failed·시도 3회 |
| 3 | 디스크 High, 아직 분석 안 됨 | `pending` | #11 에서 `report: null, evidence: [], plan: null, steps: []` |
| 4 | Info(1) | `skipped` | 분석 기준 미만 |
| 5 | CPU High, 해결됨, 분석 중 | `running` | `status: resolved` 이면서 분석 진행 |
| 6 | 네트워크 Warning, 분석 실패 | `failed` | 리포트 없음, run error |

- `action_id`의 `seed_` 값은 예시다. 실제 동작 ID는 `packs/<domain>/actions.yaml`에서 온다.
- 장애 1 계획 3단계(프로세스 강제 종료)는 `actions.yaml`에 **없는** 동작이라 `action_id`가 `NULL`이고 C다. 화면에서 "목록에 없으면 C"(SAFE-06)를 보여 주는 예시다.
- 시각은 2026-10-15 UTC 기준이다. #5의 "오늘 리포트 수"(KST 자정 기준)는 실행 날짜에 따라 0이 될 수 있다.
