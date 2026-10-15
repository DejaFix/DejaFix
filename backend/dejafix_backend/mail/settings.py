"""메일 워커 설정. 비밀값(SMTP_PASSWORD 등)은 .env / 환경 변수로만 받고 로그에 쓰지 않는다."""

from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_ATTEMPTS = 3  # FR-MAIL-004: 3회 재시도 후 failed


class MailSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DB 경로는 Backend 설정(dejafix_backend.config)을 그대로 쓴다.
    mail_provider: str = "console"  # console | smtp | sendgrid
    mail_recipients: str = ""  # 쉼표 구분. 수신자는 여기서만 온다 (SAFE-16)
    mail_from: str = ""  # 발신 계정 (TODO: 추후결정)
    mail_poll_sec: float = 30.0
    mail_retry_delay_sec: float = 2.0

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_timeout_sec: float = 10.0

    app_base_url: str = ""  # 메일 본문 링크용 (TODO: 추후결정 — 데모 호스트 PC)

    @property
    def recipients(self) -> list[str]:
        seen: list[str] = []
        for raw in self.mail_recipients.split(","):
            addr = raw.strip()
            if addr and "@" in addr and addr not in seen:
                seen.append(addr)
        return seen
