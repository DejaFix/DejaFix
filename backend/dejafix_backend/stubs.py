"""임시(스텁) 응답용 예시 JSON 로더. #5·#6 이 libs/zabbix_ro(T30) 연결 전까지 쓴다."""

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent / "examples"


def load_example(name: str) -> Any:
    """매번 새로 읽어 호출자가 수정해도 원본이 오염되지 않게 한다."""
    return json.loads((_DIR / f"{name}.json").read_text(encoding="utf-8"))
