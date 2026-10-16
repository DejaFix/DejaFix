from pathlib import Path

import pytest

from dejafix_kb.config import KbSettings
from shared_db import load_dev_seed, open_db

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture
def seeded_shared(tmp_path) -> Path:
    path = tmp_path / "shared.db"
    conn = open_db(path, "shared")
    load_dev_seed(conn, "shared")
    conn.close()
    return path


@pytest.fixture
def settings(tmp_path, seeded_shared) -> KbSettings:
    return KbSettings.from_env(
        {
            "KB_ROOT": str(REPO),
            "KB_DB_PATH": str(tmp_path / "knowledge.db"),
            "SHARED_DB_PATH": str(seeded_shared),
            "KB_DOC_DIRS": "docs/demo",
            "DOMAIN_PACK": "it",
        }
    )
