"""장애 목록·상세 성능 점검 — 장애 3천 건에서도 가볍게, 장애마다 도는 하위 조회가 인덱스를 타는지.

근거: `contracts/api.md` 1장 "응답 속도 — 프론트가 현황 홈·장애 상세를 15초마다 다시 부른다 → 1초 안에 응답".
실측(5천 건): 목록·상세 모두 15ms 이하, 5만 건에서도 `status` 필터만 약 87ms(일치 행을 임시 정렬). 데모 규모에서는 무관해서 인덱스를 더하지 않았다.
이 파일은 그 결론이 깨지는 것(하위 조회가 풀스캔으로 바뀌거나 기본 목록이 정렬을 하게 되는 회귀)을 잡는다.
시간 한도는 실측의 수십 배로 넉넉히 잡아 느린 PC에서도 흔들리지 않게 했고, 첫 호출(연결·캐시 데우기)은 재지 않는다.

실행 계획 줄은 SQLite 3.36 이상 형식(`SCAN i`, `SEARCH a USING INDEX`)과 이전 형식(`SCAN TABLE i`)을 모두 읽는다.
"""

import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from dejafix_backend.db import split_zones
from dejafix_backend.routers.incidents import DETAIL_SQL, build_list_query

N = 3000
BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def iso(seconds: int) -> str:
    return (BASE + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def big_shared(env, helpers):
    """장애 3천 건 + 90% 분석됨(run·리포트·계획), 4건 중 1건은 리포트 2개."""
    schema = split_zones(helpers.schema.read_text(encoding="utf-8"))["shared"]
    conn = sqlite3.connect(env.shared)
    conn.executescript(schema)
    incidents, runs, reports, plans = [], [], [], []
    for i in range(1, N + 1):
        ts = iso(i * 30)
        incidents.append(
            (
                i,
                str(100000 + i),
                str(2000 + i % 50),
                f"장애 {i}",
                1 + i % 5,
                "problem" if i % 7 else "resolved",
                ts,
                ts,
                ts,
            )
        )
        if i % 10:
            runs.append((f"r{i}", "analyze", i, "worker", "done", ts, ts))
            reports.append((i, i, f"r{i}", 1, "fallback", "요약", ts))
            if i % 4 == 0:
                reports.append((N + i, i, f"r{i}", 2, "fallback", "요약2", ts))
            plans.append((i, i, i, f"r{i}", f"계획 {i}", "A", ts))
    conn.executemany(
        "INSERT INTO incidents (id, zabbix_eventid, zabbix_triggerid, title, severity, status,"
        " started_at, first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?,?,?)",
        incidents,
    )
    conn.executemany(
        "INSERT INTO agent_runs (id, kind, incident_id, caller, status, started_at, finished_at)"
        " VALUES (?,?,?,?,?,?,?)",
        runs,
    )
    conn.executemany(
        "INSERT INTO analysis_reports (id, incident_id, run_id, version, kind, summary, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        reports,
    )
    conn.executemany(
        "INSERT INTO change_plans (id, incident_id, report_id, run_id, title, max_tier, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        plans,
    )
    conn.commit()
    conn.close()
    return env.shared


def explain(shared_path, sql, params) -> list[tuple[int, str]]:
    """실행 계획 줄 [(부모 id, 설명)]. 부모가 0 인 줄이 최상위(메인 쿼리), 나머지는 장애마다 도는 하위 조회 안쪽이다."""
    conn = sqlite3.connect(":memory:")
    conn.execute("ATTACH DATABASE ? AS shared", (str(shared_path),))
    rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
    conn.close()
    return [(row[1], row[3]) for row in rows]


def list_plan(shared_path, **kwargs):
    sql, params = build_list_query(
        kwargs.get("status"),
        kwargs.get("severity_min"),
        kwargs.get("after"),
        kwargs.get("limit", 101),
    )
    return explain(shared_path, sql, params)  # 라우터가 실제로 만드는 SQL 그대로


# ---------------------------------------------------------------- 실행 계획: 하위 조회는 인덱스를 탄다


CASES = {
    "기본 목록": {},
    "status 필터": {"status": "problem", "limit": 51},
    "severity 필터": {"severity_min": 4, "limit": 51},
    "커서 다음 쪽": {"after": ("2026-10-01T00:30:00Z", 50)},
}


@pytest.mark.parametrize("kwargs", list(CASES.values()), ids=list(CASES))
def test_list_subqueries_use_indexes_never_full_scans(big_shared, kwargs):
    rows = list_plan(big_shared, **kwargs)
    details = [detail for _, detail in rows]
    scans = [d for d in details if re.match(r"SCAN (TABLE )?(a2?|r|p)\b", d)]
    assert scans == [], "분석·리포트·계획 조회가 풀스캔이다:\n" + "\n".join(details)
    joined = " ".join(details)
    for alias in ("r", "a", "p"):  # 장애마다 도는 하위 조회 세 곳 모두 인덱스로 찾는다
        assert re.search(rf"SEARCH (TABLE )?{alias} USING (COVERING )?INDEX", joined), (
            details
        )


def test_detail_subqueries_use_indexes_never_full_scans(big_shared):
    rows = explain(big_shared, DETAIL_SQL, (100,))
    details = [detail for _, detail in rows]
    assert not [d for d in details if re.match(r"SCAN (TABLE )?(a2?|r|p)\b", d)], (
        details
    )
    assert any(
        re.search(r"SEARCH (TABLE )?i USING INTEGER PRIMARY KEY", d) for d in details
    ), details


def test_unfiltered_list_walks_the_started_index_and_does_not_sort(big_shared):
    """필터 없는 기본 목록은 `ix_incidents_started` 를 그대로 걸어 메인 쿼리가 정렬하지 않는다.

    `USE TEMP B-TREE FOR ORDER BY` 는 하위 조회 안쪽(버전 정렬)에는 정상으로 한 줄 나온다 — 그래서 전체 줄이 아니라
    **최상위(부모 0) 줄만** 본다. 인덱스를 지우면 최상위에 `SCAN i` 와 임시 정렬 줄이 생겨 이 테스트가 실패한다.
    """
    rows = list_plan(big_shared)
    top = [detail for parent, detail in rows if parent == 0]
    main = [d for d in top if re.match(r"(SCAN|SEARCH) (TABLE )?i\b", d)]
    assert len(main) == 1 and "ix_incidents_started" in main[0], top
    assert not any(d == "USE TEMP B-TREE FOR ORDER BY" for d in top), top


def test_the_main_sort_check_really_fails_without_the_started_index(
    env, helpers, big_shared
):
    """위 검사가 공허하지 않음을 확인한다: 인덱스를 지운 DB 에서는 최상위에 임시 정렬이 나타난다."""
    conn = sqlite3.connect(big_shared)
    conn.execute("DROP INDEX ix_incidents_started")
    conn.commit()
    conn.close()
    top = [detail for parent, detail in list_plan(big_shared) if parent == 0]
    assert "USE TEMP B-TREE FOR ORDER BY" in top, top


# ---------------------------------------------------------------- 응답 시간 (넉넉한 상한)


def timed(client, headers, path):
    started = time.perf_counter()
    response = client.get(path, headers=headers)
    return response, (time.perf_counter() - started) * 1000


@pytest.mark.parametrize(
    "path,limit_ms",
    [
        ("/api/incidents?limit=100", 500),
        ("/api/incidents?status=problem&limit=50", 500),
        ("/api/incidents?severity_min=4&limit=50", 500),
        ("/api/incidents/1500", 300),
        ("/api/incidents/1510", 300),  # 분석 없는 장애
        ("/api/dashboard/summary", 300),
    ],
)
def test_responses_stay_fast_with_three_thousand_incidents(
    make_client, helpers, big_shared, path, limit_ms
):
    client = make_client()
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    timed(client, headers, path)  # 첫 호출(연결·캐시 데우기)은 재지 않는다
    response, elapsed = timed(client, headers, path)
    assert response.status_code == 200
    assert elapsed < limit_ms, f"{path} 가 {elapsed:.0f}ms 걸렸다 (한도 {limit_ms}ms)"


def test_cursor_walk_visits_every_incident_once_and_every_page_is_fast(
    make_client, helpers, big_shared
):
    client = make_client()
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    timed(client, headers, "/api/incidents?limit=100")  # 데우기: 첫 쪽은 재지 않는다
    seen, cursor, slowest = [], None, 0.0
    while True:
        path = "/api/incidents?limit=100" + (f"&cursor={cursor}" if cursor else "")
        response, elapsed = timed(client, headers, path)
        slowest = max(slowest, elapsed)
        body = response.json()
        seen += [i["id"] for i in body["data"]]
        cursor = body["meta"]["next_cursor"]
        if not cursor:
            break
    assert len(seen) == N and len(set(seen)) == N  # 한 건도 빠지거나 겹치지 않는다
    assert seen == sorted(
        seen, reverse=True
    )  # 시드가 시간순 증가라 id 내림차순 = 최신순
    assert slowest < 500, f"가장 느린 쪽이 {slowest:.0f}ms"
