"""#10·#11 — 팀 시드(장애 6건)로 실제 DB 조회를 검증한다."""

import json

import pytest
from jsonschema import Draft202012Validator

from dejafix_backend.routers.incidents import analysis_status

# 시드 장애 6건 (libs/shared_db/fixtures/seed_dev.sql): 화면 analysis.status 6값을 하나씩 만든다
EXPECTED_STATUS = {
    1: "done",
    2: "fallback",
    3: "pending",
    4: "skipped",
    5: "running",
    6: "failed",
}
# started_at 내림차순
EXPECTED_ORDER = [3, 1, 4, 5, 2, 6]


@pytest.fixture
def api(seeded_client, helpers):
    headers = helpers.login(seeded_client, "oncall", helpers.oncall_password)

    class Api:
        def get(self, path):
            return seeded_client.get(path, headers=headers)

    return Api()


@pytest.fixture
def incident_validator(helpers):
    # contracts/incident.schema.json 은 계약 PR 로 들어온다. 그 PR 이 dev 에 머지되기 전에는
    # 이 검증만 건너뛰고(나머지 테스트는 그대로 실행), 머지된 뒤에는 항상 검증한다.
    if not helpers.incident_schema.exists():
        pytest.skip("contracts/incident.schema.json 이 아직 dev 에 없음 (계약 PR 대기)")
    schema = json.loads(helpers.incident_schema.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _keys(node):
    """응답 전체에서 쓰인 모든 키 이름."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _keys(item)


# ---------------------------------------------------------------- #10 목록


def test_list_orders_newest_first_and_maps_six_analysis_statuses(api):
    response = api.get("/api/incidents")
    assert response.status_code == 200
    data = response.json()["data"]
    assert [i["id"] for i in data] == EXPECTED_ORDER
    assert {i["id"]: i["analysis"]["status"] for i in data} == EXPECTED_STATUS
    assert response.json()["meta"] == {"next_cursor": None}


def test_list_analysis_ids(api):
    by_id = {i["id"]: i["analysis"] for i in api.get("/api/incidents").json()["data"]}
    assert by_id[1] == {"status": "done", "report_id": 1, "plan_id": 1}
    assert by_id[2] == {"status": "fallback", "report_id": 2, "plan_id": 2}
    for incident_id in (3, 4, 5, 6):
        assert by_id[incident_id]["report_id"] is None
        assert by_id[incident_id]["plan_id"] is None


def test_every_incident_matches_incident_schema(api, incident_validator):
    for incident in api.get("/api/incidents").json()["data"]:
        errors = list(incident_validator.iter_errors(incident))
        assert not errors, errors


def test_severity_label_and_tags(api):
    by_id = {i["id"]: i for i in api.get("/api/incidents").json()["data"]}
    assert by_id[1]["severity"] == {"level": 4, "label": "High"}
    assert by_id[2]["severity"] == {"level": 3, "label": "Average"}
    assert by_id[4]["severity"] == {"level": 1, "label": "Information"}
    assert by_id[1]["tags"] == [{"tag": "component", "value": "cpu"}]
    assert by_id[4]["tags"] == []
    assert by_id[1]["zabbix"] == {
        "eventid": "40301",
        "triggerid": "23601",
        "hostid": "10584",
    }
    assert by_id[1]["host"] == {"id": "10584", "name": "LAB-PC-07"}


def test_filter_by_status_and_severity(api):
    resolved = api.get("/api/incidents?status=resolved").json()["data"]
    assert [i["id"] for i in resolved] == [5]
    assert resolved[0]["resolved_at"] == "2026-10-15T01:15:00Z"
    high = api.get("/api/incidents?severity_min=4").json()["data"]
    assert [i["id"] for i in high] == [3, 1, 5]
    both = api.get("/api/incidents?status=problem&severity_min=4").json()["data"]
    assert [i["id"] for i in both] == [3, 1]


def test_cursor_pagination_walks_every_incident_once(api):
    seen: list[int] = []
    cursor = None
    pages = 0
    while True:
        path = "/api/incidents?limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = api.get(path).json()
        seen += [i["id"] for i in body["data"]]
        cursor = body["meta"]["next_cursor"]
        pages += 1
        if cursor is None:
            break
        assert len(body["data"]) == 2
    assert seen == EXPECTED_ORDER
    assert pages == 3


def test_cursor_with_filters(api):
    first = api.get("/api/incidents?severity_min=4&limit=2").json()
    assert [i["id"] for i in first["data"]] == [3, 1]
    cursor = first["meta"]["next_cursor"]
    second = api.get(f"/api/incidents?severity_min=4&limit=2&cursor={cursor}").json()
    assert [i["id"] for i in second["data"]] == [5]
    assert second["meta"]["next_cursor"] is None


@pytest.mark.parametrize(
    "query", ["cursor=garbage", "limit=0", "limit=101", "severity_min=6", "status=x"]
)
def test_list_rejects_bad_query(api, query):
    response = api.get(f"/api/incidents?{query}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_503_while_shared_db_missing(client, oncall):
    response = client.get("/api/incidents", headers=oncall)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SHARED_DB_UNAVAILABLE"
    assert client.get("/api/incidents/1", headers=oncall).status_code == 503


# ---------------------------------------------------------------- #11 상세


def test_detail_incident_matches_incident_schema(api, incident_validator):
    data = api.get("/api/incidents/1").json()["data"]
    assert not list(incident_validator.iter_errors(data["incident"]))


def test_detail_has_the_four_bundles(api):
    response = api.get("/api/incidents/1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"incident", "report", "evidence", "plan", "steps", "mail_logs"}
    assert data["incident"]["analysis"] == {
        "status": "done",
        "report_id": 1,
        "plan_id": 1,
    }
    assert response.json()["meta"] == {}


def test_detail_report(api):
    report = api.get("/api/incidents/1").json()["data"]["report"]
    assert set(report) == {
        "id",
        "version",
        "kind",
        "summary",
        "impact",
        "causes",
        "facts",
        "unknowns",
        "next_checks",
        "created_at",
    }
    assert (report["id"], report["version"], report["kind"]) == (1, 1, "llm")
    assert [c["rank"] for c in report["causes"]] == [1, 2]
    assert {c["confidence"] for c in report["causes"]} <= {"low", "medium", "high"}
    assert report["causes"][1]["evidence_ids"] == [] and (
        report["causes"][1]["confidence"] == "low"
    )
    stale = [f for f in report["facts"] if f["value"] is None]
    assert [f["unknown_reason"] for f in stale] == ["STALE"]
    assert {u["reason"] for u in report["unknowns"]} == {"NOT_COLLECTED"}


def test_every_evidence_id_in_the_response_exists_in_evidence(api):
    """수용 기준: report.causes[].evidence_ids 의 모든 ID 가 evidence[] 에 존재."""
    for incident_id in (1, 2):
        data = api.get(f"/api/incidents/{incident_id}").json()["data"]
        known = {e["id"] for e in data["evidence"]}
        referenced = set(data["report"]["impact"]["evidence_ids"])
        for cause in data["report"]["causes"]:
            referenced |= set(cause["evidence_ids"])
        for fact in data["report"]["facts"]:
            referenced |= set(fact["evidence_ids"])
        for step in data["steps"]:
            referenced |= set(step["evidence_ids"])
        assert referenced <= known, (incident_id, referenced - known)


def test_evidence_comes_from_the_reports_run_without_result_json(api):
    evidence = api.get("/api/incidents/1").json()["data"]["evidence"]
    assert [e["id"] for e in evidence] == ["ev_s1", "ev_s2", "ev_s3", "ev_s4"]  # seq 순
    assert set(evidence[0]) == {
        "id",
        "tool",
        "args",
        "ok",
        "duration_ms",
        "result_summary",
        "data_clock",
        "called_at",
    }
    assert evidence[3]["args"] == {
        "itemid": "45123",
        "time_from": "2026-10-15T00:20:00Z",
    }
    assert all(e["ok"] is True for e in evidence)


def test_failed_tool_call_is_kept_with_ok_false(api):
    evidence = api.get("/api/incidents/2").json()["data"]["evidence"]
    failed = [e for e in evidence if not e["ok"]]
    assert [e["id"] for e in failed] == ["ev_s7"]
    assert failed[0]["data_clock"] is None


def test_plan_is_preview_only_with_tiered_steps(api):
    data = api.get("/api/incidents/1").json()["data"]
    assert data["plan"]["mode"] == "preview"
    assert data["plan"]["max_tier"] == "C"
    assert data["plan"]["assumptions"] == [
        "CPU 상위 프로세스는 업무 필수 프로그램이 아님"
    ]
    steps = data["steps"]
    assert [(s["seq"], s["tier"]) for s in steps] == [(1, "A"), (2, "B"), (3, "C")]
    assert steps[1]["precheck"] and steps[1]["rollback"]  # B 는 precheck·rollback 필수
    assert steps[2]["action_id"] is None  # 미등록 동작 → C


def test_no_execute_or_run_fields_anywhere(api):
    """SAFE-04: 응답 어디에도 실행 필드가 없다."""
    for incident_id in (1, 2, 3, 5, 6):
        keys = set(_keys(api.get(f"/api/incidents/{incident_id}").json()))
        assert keys.isdisjoint({"execute", "run", "result_json"}), incident_id
    for incident in api.get("/api/incidents").json()["data"]:
        assert set(_keys(incident)).isdisjoint({"execute", "run"})


def test_mail_logs_come_from_backend_db(api):
    sent = api.get("/api/incidents/1").json()["data"]["mail_logs"]
    assert sent == [
        {
            "id": 1,
            "kind": "incident_report",
            "recipient": "oncall@example.com",
            "status": "sent",
            "attempts": 1,
            "error": None,
            "created_at": "2026-10-15T01:20:55Z",
            "sent_at": "2026-10-15T01:20:58Z",
        }
    ]
    failed = api.get("/api/incidents/2").json()["data"]["mail_logs"]
    assert (failed[0]["status"], failed[0]["attempts"]) == ("failed", 3)
    assert failed[0]["sent_at"] is None


def test_fallback_report(api):
    data = api.get("/api/incidents/2").json()["data"]
    assert data["incident"]["analysis"]["status"] == "fallback"
    assert data["report"]["kind"] == "fallback"
    assert data["report"]["causes"] == []
    assert data["plan"]["max_tier"] == "A"
    assert [s["tier"] for s in data["steps"]] == ["A"]


@pytest.mark.parametrize(
    "incident_id,status",
    [(3, "pending"), (4, "skipped"), (5, "running"), (6, "failed")],
)
def test_incident_without_report_has_empty_bundles(api, incident_id, status):
    """요청서 확인 요청 8: report:null, evidence:[], plan:null, steps:[]."""
    data = api.get(f"/api/incidents/{incident_id}").json()["data"]
    assert data["incident"]["analysis"]["status"] == status
    assert data["report"] is None
    assert data["evidence"] == []
    assert data["plan"] is None
    assert data["steps"] == []
    assert data["mail_logs"] == []


def test_resolved_incident_can_still_be_running(api):
    incident = api.get("/api/incidents/5").json()["data"]["incident"]
    assert (incident["status"], incident["analysis"]["status"]) == (
        "resolved",
        "running",
    )


def test_detail_404_and_bad_id(api):
    missing = api.get("/api/incidents/999")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {"code": "NOT_FOUND", "message": "장애를 찾을 수 없습니다"}
    }
    assert api.get("/api/incidents/abc").status_code == 422


def test_latest_report_version_wins(env, make_client, helpers):
    """같은 장애를 다시 분석하면 version 이 +1 — 최신 version 의 리포트를 쓴다."""
    import sqlite3

    client = make_client(seeded=True)
    conn = sqlite3.connect(env.shared)
    conn.execute(
        "INSERT INTO agent_runs (id, kind, incident_id, caller, status, model,"
        " started_at, finished_at) VALUES ('r_new', 'analyze', 1, 'backend', 'done',"
        " NULL, '2026-10-15T02:00:00Z', '2026-10-15T02:00:30Z')"
    )
    conn.execute(
        "INSERT INTO analysis_reports (id, incident_id, run_id, version, kind, summary,"
        " created_at) VALUES (10, 1, 'r_new', 2, 'fallback', '다시 분석',"
        " '2026-10-15T02:00:30Z')"
    )
    conn.commit()
    conn.close()
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    data = client.get("/api/incidents/1", headers=headers).json()["data"]
    assert (data["report"]["id"], data["report"]["version"]) == (10, 2)
    assert data["incident"]["analysis"]["status"] == "fallback"  # 가장 최근 run 기준
    assert data["evidence"] == []  # 새 리포트의 run 에는 tool_calls 가 없다


def _add_report_v2_and_plans(env, plans):
    """장애 1 에 version 2 리포트(id 10)와 계획들을 넣는다. plans: [(id, report_id)]"""
    import sqlite3

    conn = sqlite3.connect(env.shared)
    conn.execute(
        "INSERT INTO agent_runs (id, kind, incident_id, caller, status, model,"
        " started_at, finished_at) VALUES ('r_new', 'analyze', 1, 'backend', 'done',"
        " NULL, '2026-10-15T02:00:00Z', '2026-10-15T02:00:30Z')"
    )
    conn.execute(
        "INSERT INTO analysis_reports (id, incident_id, run_id, version, kind, summary,"
        " created_at) VALUES (10, 1, 'r_new', 2, 'fallback', '다시 분석',"
        " '2026-10-15T02:00:30Z')"
    )
    old_report = conn.execute(
        "SELECT id FROM analysis_reports WHERE incident_id = 1 AND version = 1"
    ).fetchone()[0]
    for plan_id, report_id in plans:
        conn.execute(
            "INSERT INTO change_plans (id, incident_id, report_id, run_id, title,"
            " max_tier, created_at) VALUES (?, 1, ?, 'r_new', ?, 'A',"
            " '2026-10-15T02:00:40Z')",
            (
                plan_id,
                old_report if report_id == "old" else report_id,
                f"계획 {plan_id}",
            ),
        )
    conn.commit()
    conn.close()


def test_plan_follows_the_shown_report_not_the_newest_plan_id(
    env, make_client, helpers
):
    """API 11번 계획 선택 기준: change_plans.report_id = 응답의 report.id 를 우선한다."""
    client = make_client(seeded=True)
    # 새 리포트(10)의 계획은 50, 그보다 id 가 큰 60 은 옛 리포트의 계획
    _add_report_v2_and_plans(env, [(50, 10), (60, "old")])
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    data = client.get("/api/incidents/1", headers=headers).json()["data"]
    assert data["report"]["id"] == 10
    assert data["plan"]["id"] == 50
    assert data["incident"]["analysis"]["plan_id"] == 50

    listed = client.get("/api/incidents", headers=headers).json()["data"]
    row = next(i for i in listed if i["id"] == 1)
    assert row["analysis"]["plan_id"] == 50  # 목록(API 10번)도 같은 기준


def test_plan_falls_back_to_latest_when_report_has_none(env, make_client, helpers):
    """새 리포트에 딸린 계획이 없으면 그 장애의 최신 계획을 쓴다."""
    client = make_client(seeded=True)
    _add_report_v2_and_plans(env, [(60, "old")])
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    data = client.get("/api/incidents/1", headers=headers).json()["data"]
    assert data["report"]["id"] == 10
    assert data["plan"]["id"] == 60


# ---------------------------------------------------------------- 변환표 단위 검증


@pytest.mark.parametrize(
    "run_status,report_kind,severity,expected",
    [
        (None, None, 1, "skipped"),  # 기준(기본 2) 미만
        (None, None, 2, "pending"),
        (None, None, 5, "pending"),
        ("queued", None, 4, "running"),
        ("collecting", None, 4, "running"),
        ("analyzing", None, 4, "running"),
        ("validating", None, 4, "running"),
        ("reported", "llm", 4, "running"),
        ("planning", "llm", 4, "running"),
        ("done", "llm", 4, "done"),
        ("done", "fallback", 4, "fallback"),
        ("done", None, 4, "failed"),  # done 인데 리포트가 없으면 보여 줄 결과가 없다
        ("failed", None, 4, "failed"),
        ("failed", "llm", 4, "failed"),  # 가장 최근 run 이 실패면 failed
    ],
)
def test_analysis_status_table(run_status, report_kind, severity, expected):
    assert analysis_status(run_status, report_kind, severity, 2) == expected


def test_analysis_status_respects_configured_minimum():
    assert analysis_status(None, None, 3, 4) == "skipped"
    assert analysis_status(None, None, 4, 4) == "pending"
