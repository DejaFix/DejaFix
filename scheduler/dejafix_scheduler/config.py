"""Scheduler 설정 (환경 변수만, 값은 .env). 비밀값은 여기서 읽지 않는다(Zabbix 토큰은 libs/zabbix_ro 몫)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MOCK_FILE = Path(__file__).resolve().parent / "fixtures" / "mock_zabbix.json"


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
    poll_sec: int
    zabbix_mock: bool
    mock_file: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        return cls(
            shared_db_path=Path(e.get("SHARED_DB_PATH") or "data/shared.db"),
            poll_sec=max(5, _int(e.get("INCIDENT_POLL_SEC"), 30)),
            zabbix_mock=_bool(e.get("ZABBIX_MOCK")),
            mock_file=Path(e.get("SCHEDULER_MOCK_FILE") or DEFAULT_MOCK_FILE),
        )
