"""#26·#27 해결 메모 API (Issue #153) — 성공·422·403·404·503·목록 순서·shared.db 무쓰기."""

import sqlite3

import pytest

BODY = {
    "root_cause": "백업 잡이 디스크를 채움",
    "action_taken": "수동 정리",
    "result": "정상화",
}


@pytest.fixture
def operator(seeded_client, helpers):
    return helpers.login(seeded_client, "oncall", helpers.oncall_password)


@pytest.fixture
def viewer_headers(env, seeded_client, helpers):
    helpers.add_user(env.backend, "viewer", "viewer", helpers.viewer_password)
    return helpers.login(seeded_client, "viewer", helpers.viewer_password)


def _first_incident_id(env) -> int:
    conn = sqlite3.connect(env.shared)
    try:
        return conn.execute("SELECT id FROM incidents ORDER BY id LIMIT 1").fetchone()[
            0
        ]
    finally:
        conn.close()


def test_create_and_list_note(seeded_client, operator, env):
    iid = _first_incident_id(env)
    r = seeded_client.post(f"/api/incidents/{iid}/notes", json=BODY, headers=operator)
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert r.json()["meta"] == {}
    assert data["incident_id"] == iid
    assert data["root_cause"] == BODY["root_cause"]
    assert data["author"]["display_name"] == "oncall" or data["author"]["id"] > 0
    assert data["created_at"].endswith("Z")
    assert not {"execute", "run"} & set(data)

    listed = seeded_client.get(f"/api/incidents/{iid}/notes", headers=operator)
    assert listed.status_code == 200
    assert [n["id"] for n in listed.json()["data"]] == [data["id"]]


def test_list_is_newest_first_and_per_incident(seeded_client, operator, env):
    iid = _first_incident_id(env)
    ids = []
    for text in ("첫째", "둘째", "셋째"):
        r = seeded_client.post(
            f"/api/incidents/{iid}/notes", json={"result": text}, headers=operator
        )
        ids.append(r.json()["data"]["id"])
    got = seeded_client.get(f"/api/incidents/{iid}/notes", headers=operator).json()[
        "data"
    ]
    assert [n["id"] for n in got] == ids[::-1]
    assert [n["result"] for n in got] == ["셋째", "둘째", "첫째"]
    assert got[0]["root_cause"] is None


def test_empty_list_when_no_notes(seeded_client, operator, env):
    iid = _first_incident_id(env)
    r = seeded_client.get(f"/api/incidents/{iid}/notes", headers=operator)
    assert r.status_code == 200
    assert r.json()["data"] == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"root_cause": None},
        {"root_cause": "  ", "action_taken": "", "result": "\n"},
    ],
)
def test_all_blank_is_422(seeded_client, operator, env, body):
    iid = _first_incident_id(env)
    r = seeded_client.post(f"/api/incidents/{iid}/notes", json=body, headers=operator)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_length_limit_1000(seeded_client, operator, env):
    iid = _first_incident_id(env)
    url = f"/api/incidents/{iid}/notes"
    assert (
        seeded_client.post(
            url, json={"result": "가" * 1000}, headers=operator
        ).status_code
        == 201
    )
    r = seeded_client.post(url, json={"result": "가" * 1001}, headers=operator)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.safety_regression
def test_viewer_cannot_post_but_can_get(seeded_client, viewer_headers, env):
    iid = _first_incident_id(env)
    r = seeded_client.post(
        f"/api/incidents/{iid}/notes", json=BODY, headers=viewer_headers
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"
    assert (
        seeded_client.get(
            f"/api/incidents/{iid}/notes", headers=viewer_headers
        ).status_code
        == 200
    )


def test_requires_login(seeded_client, env):
    iid = _first_incident_id(env)
    assert seeded_client.get(f"/api/incidents/{iid}/notes").status_code == 401
    assert (
        seeded_client.post(f"/api/incidents/{iid}/notes", json=BODY).status_code == 401
    )


def test_author_comes_from_token_not_body(seeded_client, operator, env):
    iid = _first_incident_id(env)
    me = seeded_client.get("/api/auth/me", headers=operator).json()["data"]
    r = seeded_client.post(
        f"/api/incidents/{iid}/notes",
        json={**BODY, "author_user_id": 9999},
        headers=operator,
    )
    assert r.status_code == 201
    assert r.json()["data"]["author"]["id"] == me["id"]


def test_unknown_incident_404(seeded_client, operator):
    for call in (
        seeded_client.get,
        lambda u, headers: seeded_client.post(u, json=BODY, headers=headers),
    ):
        r = call("/api/incidents/999999/notes", headers=operator)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "NOT_FOUND"


def test_shared_db_missing_503(client, oncall):
    r = client.post("/api/incidents/1/notes", json=BODY, headers=oncall)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SHARED_DB_UNAVAILABLE"
    assert client.get("/api/incidents/1/notes", headers=oncall).status_code == 503


def test_shared_db_untouched_and_table_exists(seeded_client, operator, env):
    iid = _first_incident_id(env)
    before = env.shared.read_bytes()
    seeded_client.post(f"/api/incidents/{iid}/notes", json=BODY, headers=operator)
    conn = sqlite3.connect(env.backend)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(resolution_notes)")]
    finally:
        conn.close()
    assert cols == [
        "id",
        "incident_id",
        "author_user_id",
        "root_cause",
        "action_taken",
        "result",
        "created_at",
    ]
    assert env.shared.read_bytes() == before
