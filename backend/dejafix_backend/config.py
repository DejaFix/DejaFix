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
    # ZABBIX_MOCK=false 일 때 libs/zabbix_ro 가 쓴다. 토큰은 .env 에만 둔다(코드·로그·응답에 쓰지 않음)
    zabbix_url: str = ""
    zabbix_api_token: str = ""
    zabbix_verify_tls: str = ""
    # 화면에서 정한 Zabbix 연결 파일 (계약 #28·#29, 결정 018). 비우면 backend.db 옆 zabbix_connection.json.
    # 이 파일이 있으면 libs/zabbix_ro 가 ZABBIX_URL·ZABBIX_API_TOKEN 대신 쓴다(Scheduler·mcp-zabbix 도 같은 경로)
    zabbix_connection_file: str = ""
    # ZABBIX_MOCK=true 일 때 어떤 상황의 목 데이터를 쓸지(libs/zabbix_ro ZABBIX_MOCK_SCENARIO). 기본 demo.
    zabbix_mock_scenario: str = "demo"
    # 화면이 15초마다 부르는 API 가 느린 Zabbix 에 같이 멈추지 않게 하는 안전장치 (dejafix_backend/zabbix.py)
    zabbix_timeout_sec: float = 5.0  # API 5번·6번 호출 한도 (health 는 3초)
    zabbix_cache_ttl_sec: float = 5.0  # 성공 응답을 재사용하는 시간
    # 실패를 붙들어 두는 시간(짧게 — 복구가 금방 보이게)
    zabbix_failure_ttl_sec: float = 2.0
    agent_url: str = "http://agent:8100"
    mcp_zabbix_url: str = "http://mcp-zabbix:8200/mcp"
    internal_token: str = ""

    # 회사 나누기 (결정 019, contracts/api.md 1장 "회사"). 비면 꺼짐(지금처럼 한 회사).
    # 값은 AXcellent 회사 ID와 같아야 한다(캣북스 설치면 catbooks)
    default_company_id: str = ""
    # X-AX-Company 머리를 따르는 계정 이름(쉼표, AXcellent 프록시가 로그인하는 viewer·admin)
    company_header_accounts: str = ""

    # 분석 대상 심각도 (analysis.status 의 skipped/pending 구분)
    analyze_min_severity: int = 2

    # 서버
    cors_origins: str = "http://localhost:5173"
    # 비어 있지 않으면 backend 가 이 폴더(Vite dist)를 정적 서빙한다(dejafix-app 이미지에서 /app/frontend-dist)
    frontend_dist: str = ""
    chat_streaming: bool = True
    chat_first_event_timeout_sec: float = 3.0
    # Agent 가 이 시간 동안 조용하면 SSE 주석 ": ping" 을 보내 프록시가 연결을 끊지 않게 한다
    chat_keepalive_sec: float = 15.0

    @property
    def zabbix_connection_path(self) -> Path:
        if self.zabbix_connection_file.strip():
            return Path(self.zabbix_connection_file.strip())
        return Path(self.backend_db_path).parent / "zabbix_connection.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
