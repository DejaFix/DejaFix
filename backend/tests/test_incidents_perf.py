"""장애 목록·상세 성능 점검 (F3, NFR-PERF-005) — 장애 3천 건에서도 가볍게, 하위 조회가 인덱스를 타는지.

실측(5천 건): 목록·상세 모두 15ms 이하, 5만 건에서도 `status` 필터만 약 87ms(일치 행을 임시 정렬). 데모 규모에서는 무관해서 인덱스를 더하지 않았다.
이 파일은 그 결론이 깨지는 것(하위 조회가 풀스캔으로 바뀌는 회귀)을 잡는다. 시간 한도는 실측의 수십 배로 넉넉히 잡아 느린 PC에서도 흔들리지 않는다.
"""

import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest

from dejafix_backend.db import split_zones
from dejafix_backend.routers.incidents import _INCIDENT_SQL

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


def plan(shared_path, where_and_order: str, params=()) -> list[str]:
    conn = sqlite3.connect(":memory:")
    conn.execute("ATTACH DATABASE ? AS shared", (str(shared_path),))
    rows = conn.execute(
        "EXPLAIN QUERY PLAN " + _INCIDENT_SQL + where_and_order, params
    ).fetchall()
    conn.close()
    return [row[3] for row in rows]


# ---------------------------------------------------------------- 실행 계획: 하위 조회는 인덱스를 탄다


@pytest.mark.parametrize(
    "where_and_order",
    [
        " ORDER BY i.started_at DESC, i.id DESC LIMIT 101",  # 기본 목록
        " WHERE i.status = 'problem' ORDER BY i.started_at DESC, i.id DESC LIMIT 51",
        " WHERE i.severity >= 4 ORDER BY i.started_at DESC, i.id DESC LIMIT 51",
        " WHERE (i.started_at < '2026-10-02T00:00:00Z' OR (i.started_at = '2026-10-02T00:00:00Z' AND i.id < 5))"
        " ORDER BY i.started_at DESC, i.id DESC LIMIT 101",  # 다음 쪽(커서)
        " WHERE i.id = 100",  # 상세
    ],
    ids=["기본 목록", "status 필터", "severity 필터", "커서 다음 쪽", "상세"],
)
def test_per_row_subqueries_use_indexes_never_full_scans(big_shared, where_and_order):
    lines = plan(big_shared, where_and_order)
    scans = [line for line in lines if re.match(r"SCAN (a2?|r|p)\b", line)]
    assert scans == [], "분석·리포트·계획 조회가 풀스캔이다:\n" + "\n".join(lines)
    # 장애마다 도는 하위 조회마다 인덱스로 찾는다
    searched = " ".join(lines)
    for table_alias in ("r", "a", "p"):
        assert re.search(rf"SEARCH {table_alias} USING (COVERING )?INDEX", searched), (
            lines
        )


def test_the_unfiltered_list_walks_the_started_index_without_sorting(big_shared):
    """기본 목록(필터 없음)은 started_at 인덱스를 타서 전체를 정렬하지 않는다."""
    lines = plan(big_shared, " ORDER BY i.started_at DESC, i.id DESC LIMIT 101")
    main = lines[0]
    assert "ix_incidents_started" in main or "ix_incidents_status" in main, lines
    assert not any("USE TEMP B-TREE FOR ORDER BY" == line for line in lines[:1]), lines


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
    timed(client, headers, path)  # 첫 호출(연결·캐시 데우기)은 빼고
    response, elapsed = timed(client, headers, path)
    assert response.status_code == 200
    assert elapsed < limit_ms, f"{path} 가 {elapsed:.0f}ms 걸렸다 (한도 {limit_ms}ms)"


def test_cursor_walk_visits_every_incident_once_and_every_page_is_fast(
    make_client, helpers, big_shared
):
    client = make_client()
    headers = helpers.login(client, "oncall", helpers.oncall_password)
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
