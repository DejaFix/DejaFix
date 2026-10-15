from pathlib import Path

import pytest

from dejafix_agent.config import Settings
from dejafix_agent.packs import load_pack

FIXTURE_PACKS = Path(__file__).parent / "fixtures" / "packs"

# 안전 회귀 세트(NFR-EVAL-001) 결과 모음. True = 기대대로 판정됨.
SAFETY_RESULTS: dict[str, list[bool]] = {"dangerous": [], "safe": []}


@pytest.fixture
def safety_results() -> dict[str, list[bool]]:
    return SAFETY_RESULTS


def pytest_terminal_summary(terminalreporter):
    d, s = SAFETY_RESULTS["dangerous"], SAFETY_RESULTS["safe"]
    if d or s:
        terminalreporter.write_line(
            f"안전 회귀: 잘못 통과 {d.count(False)}/{len(d)}, 과잉 차단 {s.count(False)}/{len(s)}"
        )


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
