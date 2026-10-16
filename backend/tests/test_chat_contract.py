"""채팅 중계 ↔ contracts/agent-api.md 대조.

문서의 이벤트 예시와 표를 **직접 읽어** 가짜 Agent 의 스트림으로 쓴다. 문서가 바뀌면(이벤트가 늘거나
필드가 달라지면) 이 테스트가 먼저 깨져서 Backend 중계 코드를 다시 보게 한다.
"""

import json
import re
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import Response

from dejafix_backend.routers.chat import get_agent_transport

CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "agent-api.md"
API_CONTRACT = Path(__file__).resolve().parents[2] / "contracts" / "api.md"

# Backend 중계 코드(chat.py)가 알고 있는 이벤트. 문서가 이 집합을 벗어나면 코드를 먼저 고친다.
KNOWN_EVENTS = ["meta", "tool_call", "tool_result", "token", "final", "error"]
TOOL_CALL_KEYS = ["id", "tool", "args", "ok", "duration_ms", "summary", "data_clock"]


def _agent_api_text() -> str:
    return CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")


def doc_events() -> list[tuple[str, str]]:
    """agent-api.md 1-2 의 이벤트 예시 블록을 [(이름, 원문 블록)] 으로."""
    match = re.search(r"```\n(event: meta\n.*?)```", _agent_api_text(), re.DOTALL)
    assert match, "agent-api.md 에서 이벤트 예시 블록을 찾지 못했다"
    blocks = [b for b in match.group(1).strip().split("\n\n") if b]
    return [(b.split("\n", 1)[0].removeprefix("event: "), b + "\n\n") for b in blocks]


def doc_table_events() -> list[str]:
    text = _agent_api_text()
    section = text[text.index("| 이벤트 | 필수 여부 |") :]
    names = []
    for line in section.split("\n")[2:]:
        found = re.match(r"\| `(\w+)` \|", line)
        if not found:
            break
        names.append(found.group(1))
    return names


def data_of(block: str) -> dict:
    return json.loads(block.split("\n")[1].removeprefix("data: "))


def stream(*, without: str) -> str:
    return "".join(b for name, b in doc_events() if name != without)


@pytest.fixture
def agent_body():
    """가짜 Agent 가 돌려줄 스트림을 테스트가 바꿔 넣는다."""
    return {"text": ""}


def chat_client(make_client, helpers, agent_body, **env):
    app = FastAPI()

    @app.post("/v1/chat")
    async def v1_chat():
        return Response(agent_body["text"], media_type="text/event-stream")

    client = make_client(**env)
    client.app.dependency_overrides[get_agent_transport] = lambda: httpx.ASGITransport(
        app=app
    )
    return client, helpers.login(client, "oncall", helpers.oncall_password)


def post(client, headers):
    return client.post("/api/chat", headers=headers, json={"message": "원인이 뭐야?"})


# ---------------------------------------------------------------- 문서 자체의 일관성


def test_doc_example_and_table_list_the_same_six_events():
    assert [name for name, _ in doc_events()] == KNOWN_EVENTS
    assert doc_table_events() == KNOWN_EVENTS


def test_api_md_chat_section_only_uses_documented_events():
    text = API_CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")
    section = text[text.index("### #18") :]
    section = section[: section.index("\n## ")]
    used = set(re.findall(r"^event: (\w+)$", section, re.MULTILINE))
    assert used <= set(KNOWN_EVENTS)


# ---------------------------------------------------------------- 스트림 모드


@pytest.mark.parametrize("without", ["error", "final"])
def test_documented_stream_is_relayed_byte_for_byte(
    make_client, helpers, agent_body, without
):
    """final 로 끝나는 스트림과 error 로 끝나는 스트림 둘 다 한 글자도 바꾸지 않는다."""
    agent_body["text"] = stream(without=without)
    client, headers = chat_client(make_client, helpers, agent_body)
    response = post(client, headers)
    assert response.status_code == 200
    assert response.text == agent_body["text"]


# ---------------------------------------------------------------- 비스트리밍 모드


def test_non_streaming_json_has_exactly_the_documented_fields(
    make_client, helpers, agent_body
):
    agent_body["text"] = stream(without="error")
    client, headers = chat_client(
        make_client, helpers, agent_body, CHAT_STREAMING="false"
    )
    response = post(client, headers)
    assert response.status_code == 200
    data = response.json()["data"]

    blocks = dict(doc_events())
    meta, final = data_of(blocks["meta"]), data_of(blocks["final"])
    call, result = data_of(blocks["tool_call"]), data_of(blocks["tool_result"])

    assert set(data) == {
        "conversation_id",
        "message_id",
        "content",
        "evidence_ids",
        "unknowns",
        "tool_calls",
    }
    assert data["conversation_id"] == meta["conversation_id"]
    assert data["message_id"] == final["message_id"]
    assert data["content"] == final["content"]
    assert data["evidence_ids"] == final["evidence_ids"]
    assert data["unknowns"] == final["unknowns"]
    assert len(data["tool_calls"]) == 1
    merged = data["tool_calls"][0]
    assert list(merged) == TOOL_CALL_KEYS
    assert merged == {
        "id": call["id"],
        "tool": call["tool"],
        "args": call["args"],
        "ok": result["ok"],
        "duration_ms": result["duration_ms"],
        "summary": result["summary"],
        "data_clock": result["data_clock"],
    }


def test_non_streaming_error_event_is_502_with_the_documented_code(
    make_client, helpers, agent_body
):
    agent_body["text"] = stream(without="final")
    client, headers = chat_client(
        make_client, helpers, agent_body, CHAT_STREAMING="false"
    )
    response = post(client, headers)
    error = data_of(dict(doc_events())["error"])
    assert response.status_code == 502
    assert response.json() == {
        "error": {"code": error["code"], "message": error["message"]}
    }


def test_tool_call_without_result_still_has_all_seven_keys(
    make_client, helpers, agent_body
):
    """tool_result 가 오지 않아도 키는 항상 있고 값만 null 이다 (프론트가 undefined 를 만나지 않게)."""
    blocks = dict(doc_events())
    agent_body["text"] = blocks["meta"] + blocks["tool_call"] + blocks["final"]
    client, headers = chat_client(
        make_client, helpers, agent_body, CHAT_STREAMING="false"
    )
    merged = post(client, headers).json()["data"]["tool_calls"][0]
    assert list(merged) == TOOL_CALL_KEYS
    assert merged["id"] == data_of(blocks["tool_call"])["id"]
    assert [merged[k] for k in ("ok", "duration_ms", "summary", "data_clock")] == [
        None,
        None,
        None,
        None,
    ]


def test_rule_based_answer_has_empty_tool_calls(make_client, helpers, agent_body):
    blocks = dict(doc_events())
    agent_body["text"] = blocks["meta"] + blocks["final"]
    client, headers = chat_client(
        make_client, helpers, agent_body, CHAT_STREAMING="false"
    )
    assert post(client, headers).json()["data"]["tool_calls"] == []
