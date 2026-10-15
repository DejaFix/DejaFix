from pathlib import Path

import pytest

from dejafix_agent.config import Settings
from dejafix_agent.packs import load_pack

FIXTURE_PACKS = Path(__file__).parent / "fixtures" / "packs"


@pytest.fixture
def packs_dir() -> Path:
    return FIXTURE_PACKS


@pytest.fixture
def test_pack():
    return load_pack("test", FIXTURE_PACKS)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings.from_env(
        {"SHARED_DB_PATH": str(tmp_path / "shared.db"), "DOMAIN_PACK": "test"}
    )
