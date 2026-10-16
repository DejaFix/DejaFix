"""인증 보안 점검 (A5, NFR-SEC-004) — test_auth.py 에 없던 빈틈을 회귀 테스트로 고정한다.

계정 존재 노출(응답·해시 검증 횟수), 긴/이상한 입력, JWT 변조·알고리즘 우회, 역할의 기준(DB), 로그에 비밀이 남지 않는지.
"""

import base64
import json
import logging

import jwt
import pytest

from dejafix_backend import security
from dejafix_backend.config import get_settings
from dejafix_backend.routers import auth as auth_router

pytestmark = pytest.mark.safety_regression


def secret() -> str:
    return get_settings().jwt_secret


def me(client, token, scheme="Bearer"):
    return client.get(
        "/api/auth/me", headers={"Authorization": f"{scheme} {token}"}
    ).status_code


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


@pytest.fixture
def token(client, helpers):
    return helpers.login(client, "oncall", helpers.oncall_password)[
        "Authorization"
    ].removeprefix("Bearer ")


# ---------------------------------------------------------------- 계정 존재 노출


def test_unknown_user_and_wrong_password_are_indistinguishable(client, helpers):
    unknown = client.post(
        "/api/auth/login", json={"username": "nobody", "password": "x"}
    )
    wrong = client.post(
        "/api/auth/login", json={"username": "oncall", "password": "wrong"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()  # 코드·메시지까지 같다


def test_password_hash_is_checked_exactly_once_even_for_an_unknown_user(
    client, helpers, monkeypatch
):
    """응답 시간으로 계정 존재를 알 수 없게 — 없는 사용자도 더미 해시로 검증을 한 번 한다 (타이밍 측정 대신 구조로 확인)."""
    calls = []
    real = auth_router.verify_password

    def spy(password, password_hash):
        calls.append(password_hash)
        return real(password, password_hash)

    monkeypatch.setattr(auth_router, "verify_password", spy)
    client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
    assert calls == [security.DUMMY_HASH]
    calls.clear()
    client.post("/api/auth/login", json={"username": "oncall", "password": "wrong"})
    assert len(calls) == 1 and calls[0] != security.DUMMY_HASH
    calls.clear()
    client.post(
        "/api/auth/login",
        json={"username": "oncall", "password": helpers.oncall_password},
    )
    assert len(calls) == 1


# ---------------------------------------------------------------- 이상한 입력은 500 이 아니라 401·422


@pytest.mark.parametrize(
    "password",
    ["a" * 72, "a" * 73, "a" * 100, "a" * 10000, "가" * 40, "", "\x00", " ", "😀" * 30],
    ids=[
        "72바이트",
        "73바이트",
        "100자",
        "1만자",
        "한글 120바이트",
        "빈 값",
        "NUL",
        "공백",
        "이모지",
    ],
)
def test_odd_passwords_are_401_never_500(client, password):
    """bcrypt 는 72바이트를 넘는 비밀번호를 예외로 거부한다 — 그 예외가 500 이 되면 안 된다."""
    response = client.post(
        "/api/auth/login", json={"username": "oncall", "password": password}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.parametrize(
    "username",
    [
        "' OR '1'='1",
        "oncall' --",
        "ONCALL",
        "oncall ",
        "",
        "x" * 100000,
        "on\x00call",
        "%",
        "oncall;DROP TABLE users",
    ],
    # 10만 자 값이 테스트 이름에 그대로 들어가면 Windows 환경 변수 한도(32767자)를 넘으므로 이름을 직접 정한다
    ids=[
        "SQL 주입",
        "주석 주입",
        "대문자",
        "끝 공백",
        "빈 이름",
        "10만자",
        "NUL",
        "퍼센트",
        "세미콜론",
    ],
)
def test_odd_usernames_are_401_and_do_not_log_anyone_in(client, helpers, username):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": helpers.oncall_password},
    )
    assert (
        response.status_code == 401
    )  # 올바른 비밀번호여도 다른 이름으로는 로그인되지 않는다 (대소문자·공백 구분)


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"username": "x"},
        {"password": "x"},
        {"username": 1, "password": 2},
        {"username": None, "password": None},
        [],
        "text",
    ],
)
def test_malformed_login_bodies_are_422(client, body):
    response = (
        client.post("/api/auth/login", json=body)
        if body is not None
        else client.post("/api/auth/login")
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------- JWT 우회·변조


def test_alg_none_token_is_rejected(client):
    unsigned = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'sub': '1', 'role': 'admin', 'exp': 4102444800})}."
    assert me(client, unsigned) == 401


def test_changing_the_role_claim_without_resigning_is_rejected(client, token):
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["role"] = "admin"
    assert me(client, f"{header}.{b64(claims)}.{signature}") == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "1"},
        {"exp": 4102444800},
        {"sub": "abc", "exp": 4102444800},
        {"sub": "", "exp": 4102444800},
    ],
    ids=["exp 없음", "sub 없음", "sub 숫자 아님", "sub 빈 값"],
)
def test_tokens_missing_required_claims_are_rejected(client, claims):
    assert me(client, jwt.encode(claims, secret(), algorithm="HS256")) == 401


def test_a_token_signed_with_another_algorithm_is_rejected(client):
    other = jwt.encode({"sub": "1", "exp": 4102444800}, secret(), algorithm="HS512")
    assert me(client, other) == 401


@pytest.mark.parametrize(
    "value",
    ["", "not-a-jwt", "a.b.c", "Bearer", "x" * 5000],
    ids=["빈 값", "JWT 아님", "a.b.c", "Bearer 단어", "5천자"],
)
def test_garbage_tokens_are_401(client, value):
    assert me(client, value) == 401


def test_only_the_bearer_scheme_is_accepted(client, token):
    assert me(client, token, scheme="Basic") == 401
    assert me(client, token, scheme="Token") == 401
    assert (
        me(client, token) == 200
    )  # 같은 토큰이 Bearer 로는 통과한다 (위 실패가 토큰 탓이 아님)


# ---------------------------------------------------------------- 역할의 기준은 DB


def test_role_comes_from_the_database_not_from_the_token(client, env, helpers, token):
    """운영자를 viewer 로 내리면 이미 받은 토큰도 바로 viewer 로 취급된다 (토큰의 role 클레임은 믿지 않는다)."""
    import sqlite3

    assert (
        client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": "x"},
        ).status_code
        != 403
    )
    conn = sqlite3.connect(env.backend)
    conn.execute("UPDATE users SET role = 'viewer' WHERE username = 'oncall'")
    conn.commit()
    conn.close()
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.get("/api/auth/me", headers=headers).json()["data"]["role"] == "viewer"
    )
    assert (
        client.post("/api/chat", headers=headers, json={"message": "x"}).status_code
        == 403
    )


# ---------------------------------------------------------------- 응답·로그에 비밀이 없다


def test_responses_never_contain_the_password_hash(client, helpers):
    login = client.post(
        "/api/auth/login",
        json={"username": "oncall", "password": helpers.oncall_password},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
    for text in (login.text, client.get("/api/auth/me", headers=headers).text):
        assert (
            "password" not in text.lower() and "$2b$" not in text and "$2a$" not in text
        )


def test_no_log_record_contains_a_password_token_or_hash(client, helpers, caplog):
    caplog.set_level(logging.DEBUG)
    secret_password = "hunter2-very-secret-pw"
    client.post(
        "/api/auth/login", json={"username": "oncall", "password": secret_password}
    )  # 실패
    ok = client.post(
        "/api/auth/login",
        json={"username": "oncall", "password": helpers.oncall_password},
    )  # 성공
    token = ok.json()["data"]["token"]
    client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    client.get("/api/auth/me", headers={"Authorization": "Bearer forged.token.value"})
    logged = "\n".join(f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records)
    for sensitive in (
        secret_password,
        helpers.oncall_password,
        token,
        "$2b$",
        "forged.token.value",
        secret(),
    ):
        assert sensitive not in logged, sensitive
