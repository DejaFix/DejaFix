import sqlite3

from dejafix_backend.config import get_settings
from dejafix_backend.security import create_token


def test_login_success_shape(client, helpers):
    response = client.post(
        "/api/auth/login",
        json={"username": "oncall", "password": helpers.oncall_password},
    )
    assert response.status_code == 200
    body = response.json()
    user = body["data"]["user"]
    assert body["data"]["token"]
    assert set(user) == {"id", "username", "role", "display_name"}
    assert (user["username"], user["role"], user["display_name"]) == (
        "oncall",
        "operator",
        "당직자",
    )
    assert body["meta"]["expires_at"].endswith("Z")
    assert "password" not in response.text


def test_login_admin_role(client, helpers):
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": helpers.admin_password},
    )
    assert response.json()["data"]["user"]["role"] == "admin"


def test_login_failure_is_401_and_does_not_reveal_which_part_was_wrong(client):
    wrong_password = client.post(
        "/api/auth/login", json={"username": "oncall", "password": "nope"}
    )
    unknown_user = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "nope"}
    )
    for response in (wrong_password, unknown_user):
        assert response.status_code == 401
        assert response.json() == {
            "error": {
                "code": "INVALID_CREDENTIALS",
                "message": "아이디 또는 비밀번호가 틀렸습니다",
            }
        }


def test_login_updates_last_login_at(env, client, helpers):
    helpers.login(client, "oncall", helpers.oncall_password)
    conn = sqlite3.connect(env.backend)
    (last,) = conn.execute(
        "SELECT last_login_at FROM users WHERE username='oncall'"
    ).fetchone()
    conn.close()
    assert last and last.endswith("Z")


def test_me(client, oncall):
    response = client.get("/api/auth/me", headers=oncall)
    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"id", "username", "display_name", "email", "role"}
    assert (data["username"], data["role"], data["email"]) == (
        "oncall",
        "operator",
        "oncall@example.com",
    )
    assert response.json()["meta"] == {}


def test_me_requires_valid_token(client):
    for headers in ({}, {"Authorization": "Bearer not-a-jwt"}):
        response = client.get("/api/auth/me", headers=headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_expired_token_is_401(client):
    token, _ = create_token(get_settings().jwt_secret, 1, "admin", expire_min=-1)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_token_for_deleted_user_is_401(env, client, oncall):
    conn = sqlite3.connect(env.backend)
    conn.execute("DELETE FROM users WHERE username='oncall'")
    conn.commit()
    conn.close()
    assert client.get("/api/auth/me", headers=oncall).status_code == 401


def test_token_signed_with_other_secret_is_401(client):
    token, _ = create_token("another-secret-another-secret-32bytes", 1, "admin", 60)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_seed_is_idempotent(env, make_client):
    make_client()
    make_client()
    conn = sqlite3.connect(env.backend)
    rows = conn.execute("SELECT username, role FROM users ORDER BY username").fetchall()
    conn.close()
    assert rows == [("admin", "admin"), ("oncall", "operator")]


def test_seed_does_not_reset_existing_password(make_client, helpers):
    make_client()
    client = make_client(DEMO_ONCALL_PASSWORD="changed-later")
    response = client.post(
        "/api/auth/login",
        json={"username": "oncall", "password": helpers.oncall_password},
    )
    assert response.status_code == 200


def test_seed_skips_account_without_password(env, make_client):
    make_client(DEMO_ADMIN_PASSWORD="")
    conn = sqlite3.connect(env.backend)
    names = [r[0] for r in conn.execute("SELECT username FROM users")]
    conn.close()
    assert names == ["oncall"]


def test_password_is_hashed_in_db(env, client, helpers):
    conn = sqlite3.connect(env.backend)
    (stored,) = conn.execute(
        "SELECT password_hash FROM users WHERE username='admin'"
    ).fetchone()
    conn.close()
    assert stored != helpers.admin_password and stored.startswith("$2")


def test_viewer_can_read_but_not_chat(client, viewer):
    """FR-BE-003: viewer 는 조회만, POST /api/chat 은 403."""
    assert client.get("/api/auth/me", headers=viewer).status_code == 200
    assert client.get("/api/dashboard/summary", headers=viewer).status_code == 200
    response = client.post("/api/chat", headers=viewer, json={"message": "안녕"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_unauthenticated_requests_are_401(client):
    for method, path in [
        ("get", "/api/health"),
        ("get", "/api/dashboard/summary"),
        ("get", "/api/problems"),
        ("get", "/api/incidents"),
        ("get", "/api/incidents/1"),
        ("post", "/api/chat"),
    ]:
        response = getattr(client, method)(path)
        assert response.status_code == 401, path
        assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_error_envelopes_for_unknown_route_and_bad_body(client, oncall):
    unknown = client.get("/api/nope", headers=oncall)
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "NOT_FOUND"

    bad = client.post("/api/auth/login", json={"username": "x"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"

    wrong_method = client.put("/api/auth/me", headers=oncall)
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
