"""LLM 요청 본문 (FR-AG-004·012): reasoning_effort 는 설정했을 때만 보낸다."""

from __future__ import annotations

from typing import Any

import pytest

from dejafix_agent import llm
from dejafix_agent.config import Settings

BASE_ENV = {
    "LLM_BASE_URL": "https://llm.invalid/v1/",
    "LLM_API_KEY": "test-key",
    "LLM_MODEL": "test-model",
}


class _Resp:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_post(url: str, json: dict[str, Any], **_: Any) -> _Resp:
        captured["url"] = url
        captured["body"] = json
        return _Resp()

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    return captured


def test_reasoning_effort_omitted_by_default(sent: dict[str, Any]) -> None:
    llm.complete_json(Settings.from_env(dict(BASE_ENV)), "p")
    assert sent["url"] == "https://llm.invalid/v1/chat/completions"
    assert "reasoning_effort" not in sent["body"]
    assert sent["body"]["max_tokens"] == llm.MAX_TOKENS


def test_reasoning_effort_sent_when_set(sent: dict[str, Any]) -> None:
    env = dict(BASE_ENV, LLM_REASONING_EFFORT=" minimal ")
    llm.complete_json(Settings.from_env(env), "p")
    assert sent["body"]["reasoning_effort"] == "minimal"
