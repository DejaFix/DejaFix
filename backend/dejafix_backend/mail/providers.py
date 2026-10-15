"""메일 공급자 (FR-MAIL-006·007). 기본은 console(실발송 없음).

- console : 로그로만 출력, mail_logs(provider='console') 기록 (개발 기본)
- smtp    : STARTTLS + 로그인. 발신 계정 MAIL_FROM 은 (TODO: 추후결정)
- sendgrid: [선택] 미구현 → 발송 실패로 기록
오류 문구에는 비밀값을 넣지 않는다.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from .settings import MailSettings

log = logging.getLogger("dejafix.backend.mail")


class MailError(RuntimeError):
    """발송 실패. 메시지는 mail_logs.error 에 그대로 들어가므로 비밀값을 넣지 않는다."""


class Provider(Protocol):
    name: str

    def send(self, recipient: str, subject: str, body: str) -> None: ...


class ConsoleProvider:
    name = "console"

    def send(self, recipient: str, subject: str, body: str) -> None:
        log.info("[메일 console] to=%s subject=%s\n%s", recipient, subject, body)


class SmtpProvider:
    name = "smtp"

    def __init__(self, settings: MailSettings):
        self.settings = settings

    def send(self, recipient: str, subject: str, body: str) -> None:
        s = self.settings
        if not s.mail_from:
            raise MailError("MAIL_FROM 미설정 (발신 계정 TODO: 추후결정)")
        msg = EmailMessage()
        msg["From"] = s.mail_from
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(
                s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_sec
            ) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            # 서버 응답에 계정 정보가 섞일 수 있어 예외 종류만 남긴다
            raise MailError(f"SMTP 발송 실패 ({type(exc).__name__})") from None


class SendgridProvider:
    name = "sendgrid"

    def send(self, recipient: str, subject: str, body: str) -> None:
        raise MailError("SendGrid 공급자는 [선택] 단계로 아직 구현되지 않음")


def make_provider(settings: MailSettings) -> Provider:
    kind = settings.mail_provider.strip().lower()
    if kind == "smtp":
        return SmtpProvider(settings)
    if kind == "sendgrid":
        return SendgridProvider()
    if kind != "console":
        log.warning("알 수 없는 MAIL_PROVIDER, console 로 대신함")
    return ConsoleProvider()
