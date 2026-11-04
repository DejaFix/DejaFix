"""API ↔ contracts/api.md 적합성 (F2) — 문서의 경로 표·역할 표·오류 코드 표를 직접 읽어 실제 응답과 맞춘다.

문서가 바뀌면(경로·역할·오류 코드) 이 테스트가 먼저 깨져서 구현을 다시 보게 한다.
"""

import re
from pathlib import Path

import pytest

API_MD = Path(__file__).resolve().parents[2] / "contracts" / "api.md"
ROLE_RANK = {"공개": 0, "로그인": 1, "viewer": 1, "operator": 2, "admin": 3}


def doc() -> str:
    return API_MD.read_text(encoding="utf-8").replace("\r\n", "\n")


def norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def doc_routes() -> list[tuple[str, str, str]]:
    """2장 표 → [(method, path, 최소 역할)]. `GET /healthz` 는 1장에 따로 있다."""
    text = doc()
    section = text[text.index("## 2. 엔드포인트 요약") :]
    section = section[: section.index("\n## 3.")]
    rows = re.findall(
        r"^\| \d+ \| `(GET|POST|PUT|PATCH|DELETE) (/[^`?]*)(?:\?[^`]*)?` \| (\S+) \|",
        section,
        re.MULTILINE,
    )
    assert len(rows) == 8, rows  # 필수 8개
    return [(m.lower(), norm(p), role) for m, p, role in rows]


def doc_error_codes() -> dict[str, int]:
    text = doc()
    section = text[text.index("### 오류 코드") :]
    section = section[: section.index("\n\n", section.index("|---"))]
    pairs = re.findall(r"^\| (\d{3}) \| `(\w+)` \|", section, re.MULTILINE)
    assert len(pairs) >= 9, pairs
    return {code: int(http) for http, code in pairs}


# ---------------------------------------------------------------- 경로


def test_exposed_routes_are_exactly_the_documented_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    exposed = {(m, norm(p)) for p, ops in paths.items() for m in ops}
    documented = {(m, p) for m, p, _ in doc_routes()} | {("get", "/healthz")}
    # [이후] 해결 메모 #26·#27 (contracts/api.md 2장 표의 '([이후])' 행, 테스트는 test_notes.py)
    documented |= {
        ("get", "/api/incidents/{}/notes"),
        ("post", "/api/incidents/{}/notes"),
    }
    assert exposed == documented


def test_healthz_is_public_and_needs_no_prefix(client):
    assert client.get("/healthz").json() == {"status": "ok"}


# ---------------------------------------------------------------- 역할


def request(client, method, path, headers=None):
    url = path.replace("{}", "1")
    body = {"message": "원인이 뭐야?"} if method == "post" else None
    return client.request(method.upper(), url, headers=headers or {}, json=body)


def test_documented_minimum_roles_are_enforced(env, make_client, helpers):
    """문서의 최소 역할대로: 토큰 없음 401(공개 제외), viewer 는 operator 경로에서 403, operator 는 통과."""
    client = make_client(seeded=True)
    helpers.add_user(env.backend, "viewer", "viewer", helpers.viewer_password)
    viewer = helpers.login(client, "viewer", helpers.viewer_password)
    operator = helpers.login(client, "oncall", helpers.oncall_password)

    for method, path, role in doc_routes():
        if path == "/api/auth/login":
            assert role == "공개"
            continue
        rank = ROLE_RANK[role]
        assert request(client, method, path).status_code == 401, (method, path)
        viewer_status = request(client, method, path, viewer).status_code
        operator_status = request(client, method, path, operator).status_code
        assert operator_status != 403, (method, path, "operator 가 막힘")
        if rank >= ROLE_RANK["operator"]:
            assert viewer_status == 403, (method, path, "viewer 가 통과함")
        else:
            assert viewer_status != 403, (method, path, "viewer 가 막힘")


# ---------------------------------------------------------------- 응답 봉투·오류 형식


def test_every_get_success_has_exactly_data_and_meta(make_client, helpers):
    client = make_client(seeded=True)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    for method, path, _ in doc_routes():
        if method != "get":
            continue
        response = request(client, method, path, headers)
        assert response.status_code == 200, path
        body = response.json()
        assert set(body) == {"data", "meta"}, path
        assert isinstance(body["meta"], dict), path


def test_error_bodies_are_the_documented_envelope_and_codes(make_client, helpers):
    """모든 오류는 {error:{code,message}} 이고 code·HTTP 상태가 문서의 표와 같다."""
    client = make_client(seeded=True)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    documented = doc_error_codes()
    cases = [
        ("get", "/api/health", None, 401),  # UNAUTHORIZED
        ("get", "/api/incidents/999999", headers, 404),  # NOT_FOUND
        ("get", "/api/no-such-route", headers, 404),  # 알 수 없는 경로
        ("get", "/api/incidents?limit=0", headers, 422),  # VALIDATION_ERROR
        ("get", "/api/incidents?cursor=%21%21", headers, 422),  # 잘못된 cursor
        ("post", "/api/chat", headers, 422),  # 빈 본문
    ]
    seen = set()
    for method, url, hdrs, status in cases:
        response = client.request(
            method.upper(),
            url,
            headers=hdrs or {},
            json={} if method == "post" else None,
        )
        assert response.status_code == status, (url, response.text)
        body = response.json()
        assert list(body) == ["error"], (url, body)
        assert set(body["error"]) == {"code", "message"}, (url, body)
        assert body["error"]["code"] in documented, (url, body["error"]["code"])
        assert documented[body["error"]["code"]] == status, (url, body["error"]["code"])
        seen.add(body["error"]["code"])
    assert seen == {"UNAUTHORIZED", "NOT_FOUND", "VALIDATION_ERROR"}


def test_wrong_password_and_forbidden_use_the_documented_codes(make_client, helpers):
    client = make_client(seeded=True)
    documented = doc_error_codes()
    bad = client.post("/api/auth/login", json={"username": "oncall", "password": "x"})
    assert (bad.status_code, bad.json()["error"]["code"]) == (
        401,
        "INVALID_CREDENTIALS",
    )
    assert documented["INVALID_CREDENTIALS"] == 401


def test_documented_codes_that_need_an_outage_are_registered_with_their_status():
    """실제로 내기 어려운 코드(502·503·500)는 표에 있는 상태 코드만 확인한다 — 구현이 같은 값을 쓰는지는 각 기능 테스트가 본다."""
    documented = doc_error_codes()
    assert documented["AGENT_UNAVAILABLE"] == 502
    assert documented["ZABBIX_UNAVAILABLE"] == 503
    assert documented["SHARED_DB_UNAVAILABLE"] == 503
    assert documented["INTERNAL_ERROR"] == 500


def test_shared_db_waiting_uses_the_documented_503(client, oncall):
    """shared.db 가 아직 없으면 API 10번·11번이 문서의 SHARED_DB_UNAVAILABLE(503)."""
    documented = doc_error_codes()
    for url in ("/api/incidents", "/api/incidents/1"):
        response = client.get(url, headers=oncall)
        assert response.status_code == documented["SHARED_DB_UNAVAILABLE"], url
        assert response.json()["error"]["code"] == "SHARED_DB_UNAVAILABLE"


# ---------------------------------------------------------------- 시각 형식


def test_incident_times_are_utc_without_fractional_seconds(make_client, helpers):
    client = make_client(seeded=True)
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    for item in client.get("/api/incidents", headers=headers).json()["data"]:
        assert pattern.match(item["started_at"]), item["started_at"]
        if item["resolved_at"] is not None:
            assert pattern.match(item["resolved_at"]), item["resolved_at"]
    meta = client.get("/api/health", headers=headers).json()["meta"]
    assert pattern.match(meta["checked_at"])


# ---------------------------------------------------------------- CORS


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/chat", "/api/health"])
def test_cors_preflight_allows_the_authorization_header(client, path):
    response = client.options(
        path,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "content-type" in allowed
