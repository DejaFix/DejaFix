"""접근 로그 — 요청마다 한 줄, 비밀이 남지 않고, 응답 모양은 바뀌지 않는다 (NFR-OBS-003)."""

import logging
import re

import pytest
from fastapi.testclient import TestClient

ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
ACCESS = "dejafix.access"


def access_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == ACCESS]


def request_id_of(line: str) -> str:
    return re.search(r"request_id=(\S+)", line).group(1)


# ---------------------------------------------------------------- 접근 로그 한 줄


def test_access_log_line_has_id_method_path_status_and_time(client, oncall, caplog):
    caplog.set_level(logging.INFO, logger=ACCESS)
    client.get("/api/health", headers=oncall)
    lines = [line for line in access_lines(caplog) if "path=/api/health " in line]
    assert len(lines) == 1
    assert re.fullmatch(
        r"access request_id=[0-9a-f]{32} method=GET path=/api/health status=200 ms=\d+",
        lines[0],
    )


def test_every_request_gets_its_own_id(client, caplog):
    caplog.set_level(logging.INFO, logger=ACCESS)
    client.get("/healthz")
    client.get("/healthz")
    ids = [request_id_of(line) for line in access_lines(caplog)]
    assert len(ids) == 2 and ids[0] != ids[1]
    assert all(ID_PATTERN.match(i) for i in ids)


@pytest.mark.parametrize("url", ["/api/health", "/api/no-such-route"])
def test_failed_requests_are_logged_with_their_real_status(client, caplog, url):
    """토큰 없음(401)·없는 경로 같은 실패도 응답의 실제 상태 코드로 남는다."""
    caplog.set_level(logging.INFO, logger=ACCESS)
    response = client.get(url)
    assert response.status_code >= 400
    lines = [line for line in access_lines(caplog) if f"path={url} " in line]
    assert len(lines) == 1 and f"status={response.status_code} " in lines[0]


def test_sse_chat_is_logged_when_the_stream_ends(client, oncall, caplog):
    """Agent 가 없어 오류 스트림이 나가는 경우에도 접근 로그가 남는다 (스트림 버퍼링 없이)."""
    caplog.set_level(logging.INFO, logger=ACCESS)
    response = client.post("/api/chat", headers=oncall, json={"message": "안녕"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert any("path=/api/chat status=200" in line for line in access_lines(caplog))


# ---------------------------------------------------------------- 응답은 바뀌지 않는다


def test_responses_do_not_carry_a_request_id_header_or_cors_exposure(client):
    """요청 ID 는 로그 안에서만 쓴다 — 계약에 없는 응답 헤더·CORS 노출을 만들지 않는다."""
    response = client.get("/healthz", headers={"Origin": "http://localhost:5173"})
    assert "x-request-id" not in response.headers
    assert (
        "x-request-id"
        not in response.headers.get("access-control-expose-headers", "").lower()
    )


# ---------------------------------------------------------------- 처리 안 된 오류 (500)


def test_unhandled_error_is_500_without_details_and_its_log_lines_pair_up(
    client, caplog
):
    def boom():
        raise RuntimeError("secret-stack-detail")

    client.app.add_api_route("/__boom", boom, methods=["GET"])
    caplog.set_level(logging.INFO)
    tolerant = TestClient(client.app, raise_server_exceptions=False)
    response = tolerant.get("/__boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-stack-detail" not in response.text  # 스택·예외 내용은 응답에 없다
    assert "x-request-id" not in response.headers

    boom_lines = [line for line in access_lines(caplog) if "path=/__boom" in line]
    assert len(boom_lines) == 1 and "status=500" in boom_lines[0]
    request_id = request_id_of(boom_lines[0])
    # 서버 오류 로그의 같은 ID 로 짝을 찾을 수 있다
    assert any(
        r.name == "dejafix.backend" and f"request_id={request_id}" in r.getMessage()
        for r in caplog.records
    )


# ---------------------------------------------------------------- 비밀은 로그에 남지 않는다


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


@pytest.mark.safety_regression
def test_uvicorn_access_log_that_prints_the_query_string_is_switched_off(client):
    """uvicorn 기본 access log 는 `GET /path?cursor=… HTTP/1.1` 처럼 쿼리를 그대로 찍는다 — 앱이 끈다."""
    assert logging.getLogger("uvicorn.access").disabled is True
