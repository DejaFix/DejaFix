"""메일 워커 (T38, FR-MAIL-001·003·004, SAFE-16).

주기마다 shared.analysis_reports(읽기 전용 ATTACH)를 보고, 아직 보내지 않은 리포트를
MAIL_RECIPIENTS 수신자별로 한 번만 보낸다.
- dedup_key = 'auto:' || report_id || ':' || recipient (UNIQUE) → 리포트당 수신자별 1통
- 실패하면 MAX_ATTEMPTS 회까지 다시 시도하고 status='failed' 로 남긴다. 워커는 계속 돈다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sqlite3
import time
from datetime import datetime, timezone

from dejafix_backend.config import get_settings
from dejafix_backend.db import open_db
from dejafix_backend.timeutil import to_iso

from . import compose
from .providers import MailError, Provider, make_provider
from .settings import MAX_ATTEMPTS, MailSettings

log = logging.getLogger("dejafix.backend.mail")

_REPORTS_SQL = """
SELECT r.id AS report_id, r.incident_id, r.kind, r.summary, r.causes_json, r.facts_json,
       r.unknowns_json, i.title, i.host_name, i.severity, i.started_at
FROM shared.analysis_reports r
JOIN shared.incidents i ON i.id = r.incident_id
ORDER BY r.id
"""
_PLAN_SQL = """
SELECT id, max_tier FROM shared.change_plans WHERE report_id = ? ORDER BY id DESC LIMIT 1
"""
_STEPS_SQL = (
    "SELECT seq, title, tier FROM shared.plan_steps WHERE plan_id = ? ORDER BY seq"
)


def dedup_key(report_id: int, recipient: str) -> str:
    return f"auto:{report_id}:{recipient}"


def _already(conn: sqlite3.Connection, key: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM main.mail_logs WHERE dedup_key = ?", (key,)
        ).fetchone()
        is not None
    )


def _send_with_retry(
    provider: Provider, recipient: str, subject: str, body: str, delay: float
) -> tuple[bool, int, str | None]:
    error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            provider.send(recipient, subject, body)
            return True, attempt, None
        except MailError as exc:
            error = str(exc)
        except Exception as exc:  # 공급자 예외로 워커가 죽지 않게. 메시지는 종류만
            error = f"발송 실패 ({type(exc).__name__})"
        log.warning("메일 발송 실패 %d/%d: %s", attempt, MAX_ATTEMPTS, error)
        if attempt < MAX_ATTEMPTS and delay > 0:
            time.sleep(delay)
    return False, MAX_ATTEMPTS, error


def run_once(
    settings: MailSettings | None = None,
    provider: Provider | None = None,
    now: datetime | None = None,
) -> int:
    """한 주기. 새로 기록한 mail_logs 행 수를 돌려준다."""
    settings = settings or MailSettings()
    recipients = settings.recipients
    if not recipients:
        log.warning("MAIL_RECIPIENTS 가 비어 있어 메일을 보내지 않음")
        return 0
    provider = provider or make_provider(settings)
    db = open_db(get_settings())
    try:
        if not db.shared_ok:
            return 0  # shared.db 가 아직 없음 (Agent·Scheduler 기동 전)
        conn = db.conn
        written = 0
        for row in conn.execute(_REPORTS_SQL).fetchall():
            pending = [
                r
                for r in recipients
                if not _already(conn, dedup_key(row["report_id"], r))
            ]
            if not pending:
                continue
            plan = conn.execute(_PLAN_SQL, (row["report_id"],)).fetchone()
            steps = conn.execute(_STEPS_SQL, (plan["id"],)).fetchall() if plan else []
            mail = compose.from_rows(row, steps, plan["max_tier"] if plan else None)
            sent_now = now or datetime.now(timezone.utc)
            subject = compose.subject(mail)
            body = compose.body(mail, settings.app_base_url, sent_now)
            for recipient in pending:
                created = to_iso(datetime.now(timezone.utc))
                ok, attempts, error = _send_with_retry(
                    provider, recipient, subject, body, settings.mail_retry_delay_sec
                )
                cur = conn.execute(
                    """INSERT OR IGNORE INTO main.mail_logs
                       (kind, incident_id, report_id, recipient, subject, provider, status,
                        attempts, error, dedup_key, created_at, sent_at)
                       VALUES ('incident_report', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        mail.incident_id,
                        mail.report_id,
                        recipient,
                        subject,
                        provider.name,
                        "sent" if ok else "failed",
                        attempts,
                        error,
                        dedup_key(mail.report_id, recipient),
                        created,
                        to_iso(datetime.now(timezone.utc)) if ok else None,
                    ),
                )
                conn.commit()
                written += cur.rowcount
        return written
    finally:
        db.close()


async def _loop(settings: MailSettings) -> None:
    while True:
        try:
            count = await asyncio.to_thread(run_once, settings)
            if count:
                log.info("메일 기록 %d건", count)
        except Exception:  # 한 주기 실패로 워커가 멈추지 않게
            log.exception("메일 워커 주기 실패, 다음 주기에 다시 시도")
        await asyncio.sleep(settings.mail_poll_sec)


def start_mail_worker(app) -> asyncio.Task:
    """lifespan 에서 호출. 태스크를 app.state.mail_worker_task 에 보관한다."""
    settings = MailSettings()
    task = asyncio.get_running_loop().create_task(_loop(settings), name="mail-worker")
    app.state.mail_worker_task = task
    log.info(
        "메일 워커 시작 (provider=%s, 수신자 %d명, %ss 주기)",
        settings.mail_provider,
        len(settings.recipients),
        settings.mail_poll_sec,
    )
    return task


async def stop_mail_worker(app) -> None:
    """lifespan 종료(yield 뒤)에서 호출. 태스크가 없으면 아무것도 안 한다."""
    task = getattr(app.state, "mail_worker_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    app.state.mail_worker_task = None
