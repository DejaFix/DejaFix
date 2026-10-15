"""#18 채팅 중계 — 가짜 Agent(ASGI)로 contracts/agent-api.md 1-2 의 Backend 중계 규칙을 검증한다."""

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from dejafix_backend.routers.chat import get_agent_transport

META = 'event: meta\ndata: {"conversation_id":"c_7f3a","run_id":"r_91b2","message_id":101}\n\n'
CALL = (
    'event: tool_call\ndata: {"id":"ev_b1","tool":"zabbix_get_history",'
    '"args":{"itemid":"45123"},"started_at":"2026-10-16T01:25:02Z"}\n\n'
)
RESULT = (
    'event: tool_result\ndata: {"id":"ev_b1","ok":true,"duration_ms":412,'
    '"summary":"최근 1시간 사용률 최대 96.1%","data_clock":"2026-10-16T01:24:30Z"}\n\n'
)
TOKEN_1 = 'event: token\ndata: {"text":"백업 작업 여부는 "}\n\n'
TOKEN_2 = 'event: token\ndata: {"text":"확인할 수 없습니다."}\n\n'
FINAL = (
    'event: final\ndata: {"message_id":102,"content":"백업 작업 여부는 확인할 수 없습니다.",'
    '"evidence_ids":["ev_b1"],"unknowns":[{"label":"백업 작업 여부","reason":"NOT_COLLECTED"}]}\n\n'
)
ERROR = 'event: error\ndata: {"code":"LLM_TIMEOUT","message":"LLM 응답이 45초 안에 오지 않았습니다"}\n\n'

FULL_STREAM = META + CALL + RESULT + TOKEN_1 + TOKEN_2 + FINAL


def make_fake_agent(seen: list[dict]) -> FastAPI:
    """메시지 문구로 동작을 고르는 가짜 Agent."""
    app = FastAPI()

    @app.post("/v1/chat")
    async def v1_chat(request: Request):
        payload = await request.json()
        seen.append({"payload": payload, "headers": dict(request.headers)})
        message = payload["message"]
        if message == "slow":
            await asyncio.sleep(0.6)
            body = FULL_STREAM
        elif message == "reject":
            return JSONResponse(
                {"error": {"code": "CONVERSATION_NOT_FOUND", "message": "대화 없음"}},
                status_code=404,
            )
        elif message == "boom":
            return JSONResponse(
                {"error": {"code": "X", "message": "x"}}, status_code=500
            )
        elif message == "agent-error":
            body = META + ERROR
        elif message == "truncated":
            body = META + TOKEN_1  # final·error 없이 끊김
        elif message == "rule-based":
            body = META + FINAL
        else:
            body = FULL_STREAM
        return Response(body, media_type="text/event-stream; charset=utf-8")

    return app


@pytest.fixture
def agent():
    seen: list[dict] = []
    return type("Agent", (), {"seen": seen, "app": make_fake_agent(seen)})()


def chat_client(make_client, helpers, agent, **env):
    client = make_client(**env)
    client.app.dependency_overrides[get_agent_transport] = lambda: httpx.ASGITransport(
        app=agent.app
    )
    return client, helpers.login(client, "oncall", helpers.oncall_password)


def events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        out.append(
            (
                lines[0].removeprefix("event: "),
                json.loads(lines[1].removeprefix("data: ")),
            )
        )
    return out


# ------------------------------------------------------------ 스트림 모드 (기본)


def test_stream_is_relayed_unchanged(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    response = client.post(
        "/api/chat",
        headers=headers,
        json={
            "conversation_id": "c_7f3a",
            "message": "백업이 원인인가?",
            "context": {"incident_id": 12},
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.text == FULL_STREAM  # 이벤트를 바꾸지 않고 그대로
    assert [name for name, _ in events(response.text)] == [
        "meta",
        "tool_call",
        "tool_result",
        "token",
        "token",
        "final",
    ]


def test_agent_receives_caller_user_headers_and_context(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    me = client.get("/api/auth/me", headers=headers).json()["data"]
    client.post(
        "/api/chat",
        headers=headers,
        json={
            "conversation_id": "c_7f3a",
            "message": "hi",
            "context": {"incident_id": 12, "hostid": "10584"},
        },
    )
    request = agent.seen[-1]
    assert request["payload"] == {
        "conversation_id": "c_7f3a",
        "message": "hi",
        "context": {"incident_id": 12, "hostid": "10584"},
        "caller": "backend",
    }
    assert request["headers"]["x-user-id"] == str(me["id"])
    assert request["headers"]["x-user-role"] == "operator"
    assert "x-internal-token" not in request["headers"]
    assert (
        "authorization" not in request["headers"]
    )  # 사용자 JWT 는 Agent 로 넘기지 않는다


def test_new_conversation_omits_conversation_id(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    client.post("/api/chat", headers=headers, json={"message": "새 대화"})
    payload = agent.seen[-1]["payload"]
    assert "conversation_id" not in payload
    assert payload["context"] == {}


def test_internal_token_is_sent_only_when_configured(make_client, helpers, agent):
    client, headers = chat_client(
        make_client, helpers, agent, INTERNAL_TOKEN="shared-secret"
    )
    client.post("/api/chat", headers=headers, json={"message": "hi"})
    assert agent.seen[-1]["headers"]["x-internal-token"] == "shared-secret"


def test_rule_based_answer_meta_then_final_is_fine(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    response = client.post("/api/chat", headers=headers, json={"message": "rule-based"})
    assert [name for name, _ in events(response.text)] == ["meta", "final"]


def test_agent_error_event_is_relayed_as_is(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    response = client.post(
        "/api/chat", headers=headers, json={"message": "agent-error"}
    )
    assert response.status_code == 200
    assert response.text == META + ERROR


def test_stream_that_ends_without_final_gets_closed_with_error(
    make_client, helpers, agent
):
    client, headers = chat_client(make_client, helpers, agent)
    response = client.post("/api/chat", headers=headers, json={"message": "truncated"})
    parsed = events(response.text)
    assert [name for name, _ in parsed] == ["meta", "token", "error"]
    assert parsed[-1][1]["code"] == "AGENT_UNAVAILABLE"


def test_no_first_event_within_timeout_is_agent_unavailable(
    make_client, helpers, agent
):
    client, headers = chat_client(
        make_client, helpers, agent, CHAT_FIRST_EVENT_TIMEOUT_SEC="0.1"
    )
    response = client.post("/api/chat", headers=headers, json={"message": "slow"})
    assert response.status_code == 200
    assert events(response.text) == [
        (
            "error",
            {"code": "AGENT_UNAVAILABLE", "message": "Agent에 연결할 수 없습니다"},
        )
    ]


def test_agent_5xx_is_agent_unavailable_event(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    response = client.post("/api/chat", headers=headers, json={"message": "boom"})
    assert [(n, d["code"]) for n, d in events(response.text)] == [
        ("error", "AGENT_UNAVAILABLE")
    ]


def test_agent_4xx_before_stream_is_passed_through(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent)
    response = client.post(
        "/api/chat",
        headers=headers,
        json={"conversation_id": "c_nope", "message": "reject"},
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "CONVERSATION_NOT_FOUND", "message": "대화 없음"}
    }


def test_connection_refused_is_agent_unavailable_event(client, oncall):
    # env 의 AGENT_URL 은 닫힌 포트, 가짜 Agent 도 끼우지 않았다
    response = client.post("/api/chat", headers=oncall, json={"message": "hi"})
    assert response.status_code == 200
    assert [(n, d["code"]) for n, d in events(response.text)] == [
        ("error", "AGENT_UNAVAILABLE")
    ]


def test_empty_message_is_422(client, oncall):
    response = client.post("/api/chat", headers=oncall, json={"message": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ------------------------------------------------------------ 비스트리밍 (탈출 규칙 1)


def test_non_streaming_merges_the_stream_into_one_json(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent, CHAT_STREAMING="false")
    response = client.post(
        "/api/chat",
        headers=headers,
        json={"conversation_id": "c_7f3a", "message": "hi"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "data": {
            "conversation_id": "c_7f3a",
            "message_id": 102,
            "content": "백업 작업 여부는 확인할 수 없습니다.",
            "evidence_ids": ["ev_b1"],
            "unknowns": [{"label": "백업 작업 여부", "reason": "NOT_COLLECTED"}],
            "tool_calls": [
                {
                    "id": "ev_b1",
                    "tool": "zabbix_get_history",
                    "args": {"itemid": "45123"},
                    "ok": True,
                    "duration_ms": 412,
                    "summary": "최근 1시간 사용률 최대 96.1%",
                    "data_clock": "2026-10-16T01:24:30Z",
                }
            ],
        },
        "meta": {},
    }


def test_non_streaming_rule_based_has_empty_tool_calls(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent, CHAT_STREAMING="false")
    data = client.post(
        "/api/chat", headers=headers, json={"message": "rule-based"}
    ).json()["data"]
    assert data["tool_calls"] == []
    assert data["conversation_id"] == "c_7f3a" and data["message_id"] == 102


def test_non_streaming_error_event_is_502_with_its_code(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent, CHAT_STREAMING="false")
    response = client.post(
        "/api/chat", headers=headers, json={"message": "agent-error"}
    )
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "LLM_TIMEOUT",
            "message": "LLM 응답이 45초 안에 오지 않았습니다",
        }
    }


@pytest.mark.parametrize("message", ["truncated", "boom"])
def test_non_streaming_broken_agent_is_502_agent_unavailable(
    make_client, helpers, agent, message
):
    client, headers = chat_client(make_client, helpers, agent, CHAT_STREAMING="false")
    response = client.post("/api/chat", headers=headers, json={"message": message})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"


def test_non_streaming_agent_4xx_is_passed_through(make_client, helpers, agent):
    client, headers = chat_client(make_client, helpers, agent, CHAT_STREAMING="false")
    response = client.post("/api/chat", headers=headers, json={"message": "reject"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"


def test_non_streaming_connection_refused_is_502(make_client, helpers):
    client = make_client(CHAT_STREAMING="false")
    headers = helpers.login(client, "oncall", helpers.oncall_password)
    response = client.post("/api/chat", headers=headers, json={"message": "hi"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AGENT_UNAVAILABLE"
