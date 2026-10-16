"""설정. 값은 환경 변수에서만 읽는다. 비어 있으면 그 기능을 끈다(기존 동작 유지)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KbSettings:
    root: Path  # 저장소 루트. 상대 경로(DB·문서)는 여기 기준
    kb_db_path: Path
    shared_db_path: Path
    doc_dirs: tuple[str, ...]
    domain_pack: str | None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "KbSettings":
        e = os.environ if env is None else env
        dirs = e.get("KB_DOC_DIRS") or "docs/demo,docs/zabbix"
        return cls(
            root=Path(e.get("KB_ROOT") or ".").resolve(),
            kb_db_path=Path(e.get("KB_DB_PATH") or "data/knowledge.db"),
            shared_db_path=Path(e.get("SHARED_DB_PATH") or "data/shared.db"),
            doc_dirs=tuple(d.strip() for d in dirs.split(",") if d.strip()),
            domain_pack=e.get("DOMAIN_PACK") or None,
        )

    def path(self, p: Path) -> Path:
        return p if p.is_absolute() else self.root / p
