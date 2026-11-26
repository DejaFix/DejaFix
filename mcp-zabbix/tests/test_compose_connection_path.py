"""compose 의 mcp-zabbix 도 backend·scheduler 와 같은 Zabbix 연결 파일 자리를 본다 (결정 018, 리뷰 11/26).

환경 변수가 없으면 zabbix_ro 는 연결 파일을 못 찾아 .env 연결만 쓰고, 화면에서 바꾼 Zabbix 가
분석·채팅(mcp-zabbix)에 안 들어간다.
"""

from pathlib import Path

import zabbix_ro.connection as conn

COMPOSE = Path(__file__).resolve().parents[2] / "infra" / "docker-compose.yml"


def _service_env(name: str) -> dict[str, str]:
    import yaml

    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    env = doc["services"][name].get("environment") or {}
    return {str(k): str(v) for k, v in env.items()}


def test_mcp_zabbix_and_backend_share_the_connection_file():
    mcp = conn.connection_path(_service_env("mcp-zabbix"))
    backend = conn.connection_path(_service_env("backend"))
    scheduler = conn.connection_path(_service_env("scheduler"))
    assert mcp is not None
    assert mcp == backend == scheduler
