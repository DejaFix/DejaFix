"""Agent 설정. 값은 환경 변수(.env)에서만 읽는다. 비밀값을 로그에 남기지 않는다."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# 활성 도메인 팩 기본값은 이 한 곳에만 둔다 (NFR-EXT-002, 루트 CLAUDE.md ⑨).
DEFAULT_DOMAIN_PACK = "it"


def _bool(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    shared_db_path: Path
    mcp_zabbix_url: str
    internal_token: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_fallback_model: str
    llm_timeout_sec: int
    llm_reasoning_effort: str
    llm_fake: bool
    domain_pack: str
    analyze_min_severity: int

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env
        return cls(
            shared_db_path=Path(e.get("SHARED_DB_PATH") or "data/shared.db"),
            mcp_zabbix_url=e.get("MCP_ZABBIX_URL", ""),
            internal_token=e.get("INTERNAL_TOKEN", ""),
            llm_base_url=e.get("LLM_BASE_URL", ""),
            llm_api_key=e.get("LLM_API_KEY", ""),
            llm_model=e.get("LLM_MODEL", ""),
            llm_fallback_model=e.get("LLM_FALLBACK_MODEL", ""),
            llm_timeout_sec=_int(e.get("LLM_TIMEOUT_SEC"), 45),
            llm_reasoning_effort=(e.get("LLM_REASONING_EFFORT") or "").strip(),
            llm_fake=_bool(e.get("LLM_FAKE")),
            domain_pack=e.get("DOMAIN_PACK") or DEFAULT_DOMAIN_PACK,
            analyze_min_severity=_int(e.get("ANALYZE_MIN_SEVERITY"), 2),
        )

    @property
    def llm_mode(self) -> str:
        """LLM 동작 모드 (FR-AG-013, 기획서 4-5): fake > fallback(키·URL 빈 값) > real."""
        if self.llm_fake:
            return "fake"
        if not self.llm_api_key or not self.llm_base_url:
            return "fallback"
        return "real"

    @property
    def model_label(self) -> str | None:
        """/healthz 와 agent_runs.model 에 쓰는 값. fallback 이면 None."""
        mode = self.llm_mode
        if mode == "fake":
            return "fake"
        if mode == "real":
            return self.llm_model or None
        return None
