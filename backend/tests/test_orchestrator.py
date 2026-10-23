"""총괄 읽기 중계 (#26·#27) — 가짜 총괄(ASGI)로 contracts/api.md 6장 규칙을 검증한다.

읽기 전용(총괄로는 GET 두 개만), 응답은 그대로 중계(단계 `output`만 제거), 관리자만, 총괄이 없으면 503.
"""

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from dejafix_backend.routers.orchestrator import get_orchestrator_transport

INCIDENT = {
    "context_id": "ctx_inc_abc",
    "title": "payment 장애 감지",
    "status": "resolved",
    "steps": [
        {
            "step_id": "diagnose",
            "label": "원인 진단",
            "status": "completed",
            "output": {"x": 1},
        },
        {
            "step_id": "record",
            "label": "사건 기록",
            "status": "completed",
            "output": {},
        },
    ],
    "events": [{"at": "2026-10-23T01:00:00Z", "message": "사건 시작"}],
    "summary": ["원인 진단 [infra] 완료"],
    "metrics": {"mttr_seconds": 4.2},
}
DEPARTMENT = {
    "name": "marketing",
    "owner": "재헌",
    "mode": "mock",
    "available": True,
    "skills": [],
    "usage": {"calls": 3, "success_rate": 1.0},
    "series": [],
    "recent": [],
}


def make_fake_orchestrator(
    seen: list[tuple[str, str]], *, down: bool = False
) -> FastAPI:
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def anything(path: str, request: Request):
        seen.append((request.method, "/" + path))
        if down:
            return PlainTextResponse("nope", status_code=500)
        if path == "api/incidents":
            return JSONResponse({"data": [INCIDENT], "meta": {"mock": True}})
        if path == "api/departments":
            return JSONResponse(
                {
                    "data": [DEPARTMENT],
                    "meta": {"mock": True, "window_seconds": 600, "bucket_seconds": 30},
                }
            )
        return JSONResponse({"error": {"code": "NOT_FOUND"}}, status_code=404)

    return app


@pytest.fixture
def orch():
    seen: list[tuple[str, str]] = []
    return type("Orch", (), {"seen": seen, "app": make_fake_orchestrator(seen)})()


def orch_client(make_client, helpers, app, role="admin", **env):
    client = make_client(ORCHESTRATOR_URL="http://orchestrator.test", **env)
    client.app.dependency_overrides[get_orchestrator_transport] = lambda: (
        httpx.ASGITransport(app=app)
    )
    password = {"admin": helpers.admin_password, "oncall": helpers.oncall_password}[
        role
    ]
    return client, helpers.login(
        client, "admin" if role == "admin" else "oncall", password
    )


def test_incidents_are_relayed_without_step_output(make_client, helpers, orch):
    client, headers = orch_client(make_client, helpers, orch.app)
    response = client.get("/api/orchestrator/incidents", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["source"] == "orchestrator" and body["meta"]["mock"] is True
    incident = body["data"][0]
    assert (
        incident["context_id"] == "ctx_inc_abc"
        and incident["summary"] == INCIDENT["summary"]
    )
    assert incident["metrics"] == {"mttr_seconds": 4.2}  # 값은 그대로
    assert all("output" not in step for step in incident["steps"])
    assert [s["step_id"] for s in incident["steps"]] == ["diagnose", "record"]


def test_departments_are_relayed_unchanged(make_client, helpers, orch):
    client, headers = orch_client(make_client, helpers, orch.app)
    response = client.get("/api/orchestrator/departments", headers=headers)
    body = response.json()
    assert response.status_code == 200 and body["data"] == [DEPARTMENT]
    assert (
        body["meta"]["window_seconds"] == 600 and body["meta"]["bucket_seconds"] == 30
    )


@pytest.mark.safety_regression
def test_only_two_read_requests_ever_reach_the_orchestrator(make_client, helpers, orch):
    client, headers = orch_client(make_client, helpers, orch.app)
    client.get("/api/orchestrator/incidents", headers=headers)
    client.get("/api/orchestrator/departments", headers=headers)
    assert orch.seen == [("GET", "/api/incidents"), ("GET", "/api/departments")]
    # 쓰기·승인·장애 주입 경로는 중계하지 않는다
    for method in ("post", "put", "patch", "delete"):
        for path in ("incidents", "departments", "demo/incidents", "holds/rollback"):
            response = getattr(client, method)(
                f"/api/orchestrator/{path}", headers=headers
            )
            assert response.status_code in (404, 405)
    assert len(orch.seen) == 2


@pytest.mark.safety_regression
def test_only_admin_can_read(make_client, helpers, orch):
    client, headers = orch_client(make_client, helpers, orch.app, role="oncall")
    for path in ("incidents", "departments"):
        assert (
            client.get(f"/api/orchestrator/{path}", headers=headers).status_code == 403
        )
        assert client.get(f"/api/orchestrator/{path}").status_code == 401
    assert orch.seen == []


def test_not_configured_is_503_not_invented_data(make_client, helpers):
    client = make_client(ORCHESTRATOR_URL="")
    headers = helpers.login(client, "admin", helpers.admin_password)
    response = client.get("/api/orchestrator/incidents", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ORCHESTRATOR_UNAVAILABLE"


def test_orchestrator_error_and_unreachable_are_503(make_client, helpers):
    seen: list = []
    client, headers = orch_client(
        make_client, helpers, make_fake_orchestrator(seen, down=True)
    )
    response = client.get("/api/orchestrator/departments", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ORCHESTRATOR_UNAVAILABLE"

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    client.app.dependency_overrides[get_orchestrator_transport] = lambda: (
        httpx.MockTransport(refuse)
    )
    again = client.get("/api/orchestrator/incidents", headers=headers)
    assert again.status_code == 503
    assert again.json()["error"]["code"] == "ORCHESTRATOR_UNAVAILABLE"


def test_unexpected_shape_is_503(make_client, helpers):
    app = FastAPI()

    @app.get("/api/incidents")
    async def incidents():
        return {"data": {"not": "a list"}, "meta": {}}

    client, headers = orch_client(make_client, helpers, app)
    assert client.get("/api/orchestrator/incidents", headers=headers).status_code == 503
