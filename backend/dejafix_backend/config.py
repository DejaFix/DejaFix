"""환경 변수 설정. 비밀값은 코드에 쓰지 않고 .env / 환경 변수로만 받는다."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/dejafix_backend/config.py -> 저장소 루트. .env·상대 DB 경로는 실행 위치(cwd)가 아니라 여기 기준.
ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # 인증
    jwt_secret: str = ""
    jwt_expire_min: int = 480
    demo_admin_password: str = ""
    demo_oncall_password: str = ""

    # DB (compose에서는 /data/*.db, 로컬 기본은 저장소 루트의 ./data/)
    backend_db_path: str = "data/backend.db"
    shared_db_path: str = "data/shared.db"
    # 비워 두면 저장소 루트의 contracts/db-schema.sql
    db_schema_path: str = ""

    # 외부 서비스
    zabbix_mock: bool = True
    agent_url: str = "http://agent:8100"
    mcp_zabbix_url: str = "http://mcp-zabbix:8200/mcp"
    internal_token: str = ""

    # 분석 대상 심각도 (analysis.status 의 skipped/pending 구분)
    analyze_min_severity: int = 2

    # 서버
    cors_origins: str = "http://localhost:5173"
    chat_streaming: bool = True
    chat_first_event_timeout_sec: float = 3.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
