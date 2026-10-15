"""LLM 호출 (T52, FR-AG-004·012·013). OpenAI 호환 API 하나만 쓴다. 공급자 고유 의존 없음.

동작 모드는 config.Settings.llm_mode:
- fake: 네트워크 없이 고정 초안(테스트·개발 전용, 데모 금지, agent_runs.model='fake')
- fallback: 호출하지 않는다 (LLM_NOT_CONFIGURED)
- real: {LLM_BASE_URL}/chat/completions 1회, max_tokens 2000, 타임아웃 LLM_TIMEOUT_SEC
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from .config import Settings

MAX_TOKENS = 2000


class LlmError(RuntimeError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code  # LLM_TIMEOUT | LLM_ERROR | LLM_NOT_CONFIGURED


def _extract_json(text: str) -> Any:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.S)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


def complete_json(settings: Settings, prompt: str) -> Any:
    """실 LLM 1회 호출 → JSON. 실패는 LlmError 로만 올린다(원문 예외를 넘기지 않음)."""
    content = complete_text(settings, prompt)
    try:
        return _extract_json(content)
    except ValueError as exc:
        raise LlmError("LLM_ERROR", "응답을 JSON으로 읽을 수 없음") from exc


def complete_text(settings: Settings, prompt: str) -> str:
    """실 LLM 1회 호출 → 응답 문자열."""
    if settings.llm_mode != "real":
        raise LlmError("LLM_NOT_CONFIGURED")
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0,
    }
    try:
        resp = httpx.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_sec,
        )
    except httpx.TimeoutException as exc:
        raise LlmError("LLM_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise LlmError("LLM_ERROR", type(exc).__name__) from exc
    if resp.status_code != 200:
        raise LlmError("LLM_ERROR", f"HTTP {resp.status_code}")
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LlmError("LLM_ERROR", "응답 형식을 읽을 수 없음") from exc
    if not isinstance(content, str) or not content.strip():
        raise LlmError("LLM_ERROR", "빈 응답")
    return content


def fake_draft(base_draft: dict[str, Any], evidence_ids: list[str]) -> dict[str, Any]:
    """가짜 LLM: fallback 초안에 근거 있는 원인 1개를 붙인 고정 응답 (FR-AG-013)."""
    draft = json.loads(json.dumps(base_draft))
    draft["report"]["causes"] = [
        {
            "rank": 1,
            "title": "가짜 LLM 원인 (테스트용)",
            "confidence": "low",
            "reasoning": "LLM_FAKE=true 고정 응답입니다. 데모에 쓰지 않습니다.",
            "evidence_ids": evidence_ids[:1],
            "verify": "실제 원인은 사람이 확인",
        }
    ]
    draft["report"]["unknowns"] = [
        u for u in draft["report"]["unknowns"] if u["label"] != "원인"
    ]
    return draft
