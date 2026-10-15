"""요청 ID(`X-Request-Id`)와 접근 로그 — 모든 응답에 붙고, 로그에 비밀이 남지 않는다 (NFR-OBS-002)."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ACCESS = "dejafix.access"


def access_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == ACCESS]


# ---------------------------------------------------------------- 응답 헤더


def test_every_kind_of_response_has_a_request_id(client, oncall):
    responses = [
        client.get("/healthz"),  # 200
        client.get("/api/health", headers=oncall),  # 200
        client.get("/api/health"),  # 401
        client.get("/api/no-such-route", headers=oncall),  # 404
        client.get("/api/incidents?limit=0", headers=oncall),  # 422
        client.post("/api/auth/login", json={"username": "x", "password": "y"}),  # 401
    ]
    for response in responses:
        assert ID_PATTERN.match(response.headers["x-request-id"]), response.status_code


def test_ids_differ_between_requests(client):
    first = client.get("/healthz").headers["x-request-id"]
    second = client.get("/healthz").headers["x-request-id"]
    assert first != second


def test_sse_stream_response_has_a_request_id(client, oncall):
    """Agent 가 없어 AGENT_UNAVAILABLE 오류 스트림이 나가는 경우에도 헤더가 붙는다."""
    response = client.post("/api/chat", headers=oncall, json={"message": "안녕"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert ID_PATTERN.match(response.headers["x-request-id"])


def test_a_safe_incoming_id_is_kept(client):
    response = client.get("/healthz", headers={"X-Request-Id": "demo-rehearsal_01.a"})
    assert response.headers["x-request-id"] == "demo-rehearsal_01.a"


@pytest.mark.parametrize(
    "bad", ["has space", "x" * 65, "<script>alert(1)</script>", "a,b"]
)
def test_an_unsafe_incoming_id_is_replaced(client, bad):
    response = client.get("/healthz", headers={"X-Request-Id": bad})
    assert response.headers["x-request-id"] != bad
    assert ID_PATTERN.match(response.headers["x-request-id"])


def test_unhandled_error_is_500_without_details_but_with_the_id(client, caplog):
    def boom():
        raise RuntimeError("secret-stack-detail")

    client.app.add_api_route("/__boom", boom, methods=["GET"])
    caplog.set_level(logging.INFO)
    tolerant = TestClient(client.app, raise_server_exceptions=False)
    response = tolerant.get("/__boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-stack-detail" not in response.text  # 스택·예외 내용은 응답에 없다
    request_id = response.headers["x-request-id"]
    assert ID_PATTERN.match(request_id)
    lines = access_lines(caplog)
    assert any(
        f"request_id={request_id}" in line and "status=500" in line for line in lines
    )
    # 서버 로그의 오류 줄에서 같은 ID 로 찾을 수 있다
    assert any(
        f"request_id={request_id}" in r.getMessage() and r.name == "dejafix.backend"
        for r in caplog.records
    )


def test_cors_exposes_the_request_id_header_to_the_browser(client):
    response = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_cors_preflight_also_carries_the_id(client):
    response = client.options(
        "/api/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert ID_PATTERN.match(response.headers["x-request-id"])


# ---------------------------------------------------------------- 접근 로그


def test_access_log_line_has_id_method_path_status_and_time(client, oncall, caplog):
    caplog.set_level(logging.INFO, logger=ACCESS)
    response = client.get("/api/health", headers=oncall)
    request_id = response.headers["x-request-id"]
    line = next(text for text in access_lines(caplog) if request_id in text)
    assert re.fullmatch(
        rf"access request_id={request_id} method=GET path=/api/health status=200 ms=\d+",
        line,
    )


@pytest.mark.safety_regression
def test_access_log_never_contains_query_token_password_or_body(
    client, oncall, helpers, caplog
):
    caplog.set_level(logging.INFO, logger=ACCESS)
    token = oncall["Authorization"].removeprefix("Bearer ")
    client.get("/api/incidents?cursor=SECRET-CURSOR-123&limit=5", headers=oncall)
    client.post(
        "/api/auth/login", json={"username": "oncall", "password": "wrong-hunter2-pass"}
    )
    client.post("/api/chat", headers=oncall, json={"message": "비공개-채팅-내용"})
    text = "\n".join(access_lines(caplog))
    assert (
        "/api/incidents" in text and "/api/auth/login" in text and "/api/chat" in text
    )
    for secret in (
        "SECRET-CURSOR-123",  # 쿼리 문자열
        "wrong-hunter2-pass",  # 로그인 비밀번호
        helpers.oncall_password,
        token,  # Authorization 헤더 값
        "Bearer",
        "비공개-채팅-내용",  # 채팅 본문
    ):
        assert secret not in text, secret


@pytest.mark.safety_regression
def test_control_characters_in_the_path_cannot_forge_log_lines(client, caplog):
    caplog.set_level(logging.INFO, logger=ACCESS)
    client.get("/api/x%0Aaccess%20request_id=forged%20status=200")
    lines = access_lines(caplog)
    assert lines and all("\n" not in line and "\r" not in line for line in lines)
    assert not any(line.startswith("access request_id=forged") for line in lines)


def test_failed_request_is_logged_with_its_status(client, caplog):
    caplog.set_level(logging.INFO, logger=ACCESS)
    client.get("/api/health")  # 토큰 없음
    assert any("path=/api/health status=401" in line for line in access_lines(caplog))
