"""메일 워커 (T38·T39, FR-MAIL-001~005·007, SAFE-16). 실제 SMTP 호출 없음."""

import asyncio
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from dejafix_backend.config import get_settings
from dejafix_backend.db import init_backend_db, split_zones
from dejafix_backend.mail import run_once, start_mail_worker, stop_mail_worker
from dejafix_backend.mail import compose, providers
from dejafix_backend.mail.settings import MAX_ATTEMPTS, MailSettings

NOW = datetime(2026, 10, 15, 1, 21, 0, tzinfo=timezone.utc)


class Recorder:
    name = "console"

    def __init__(self):
        self.sent = []

    def send(self, recipient, subject, body):
        self.sent.append((recipient, subject, body))


class Failing:
    name = "smtp"

    def __init__(self):
        self.calls = 0

    def send(self, recipient, subject, body):
        self.calls += 1
        raise providers.MailError("SMTP 발송 실패 (ConnectionRefusedError)")


@pytest.fixture
def dbs(env, helpers):
    """시드 리포트 2건이 있는 shared.db + 빈 backend.db(mail_logs 비어 있음)."""
    helpers.build_shared_db(env.shared)
    init_backend_db(get_settings())
    return env


def settings(**kw):
    base = {
        "mail_recipients": "a@example.com, b@example.com",
        "mail_retry_delay_sec": 0,
    }
    base.update(kw)
    return MailSettings(**base)


def mail_rows(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM mail_logs ORDER BY id")]
    finally:
        conn.close()


def test_dedup_one_mail_per_report_per_recipient(dbs):
    # 필수 안전 테스트: 같은 리포트에 워커 3회 → 수신자당 1행 (SAFE-16, FR-MAIL-003)
    rec = Recorder()
    first = run_once(settings(), rec, NOW)
    assert first == 4  # 리포트 2건 × 수신자 2명
    assert run_once(settings(), rec, NOW) == 0
    assert run_once(settings(), rec, NOW) == 0
    rows = mail_rows(dbs.backend)
    assert len(rows) == 4 and len(rec.sent) == 4
    assert {r["dedup_key"] for r in rows} == {
        f"auto:{rid}:{who}"
        for rid in (1, 2)
        for who in ("a@example.com", "b@example.com")
    }
    assert all(r["status"] == "sent" and r["attempts"] == 1 for r in rows)
    assert all(r["kind"] == "incident_report" and r["sent_at"] for r in rows)


def test_retry_three_times_then_failed(dbs):
    fail = Failing()
    run_once(settings(mail_recipients="a@example.com"), fail, NOW)
    assert fail.calls == 2 * MAX_ATTEMPTS  # 리포트 2건, 각 3회
    rows = mail_rows(dbs.backend)
    assert [r["status"] for r in rows] == ["failed", "failed"]
    assert all(r["attempts"] == MAX_ATTEMPTS and r["sent_at"] is None for r in rows)
    assert "SMTP" in rows[0]["error"]
    # 실패도 기록했으므로 다음 주기에 다시 보내지 않는다
    assert run_once(settings(mail_recipients="a@example.com"), fail, NOW) == 0


def test_recipients_only_from_env(dbs):
    rec = Recorder()
    run_once(
        settings(mail_recipients="a@example.com, not-an-email, a@example.com"), rec, NOW
    )
    assert {to for to, _, _ in rec.sent} == {"a@example.com"}


def test_no_recipients_sends_nothing(dbs):
    rec = Recorder()
    assert run_once(settings(mail_recipients=""), rec, NOW) == 0
    assert rec.sent == [] and mail_rows(dbs.backend) == []


def test_console_provider_is_default(dbs, monkeypatch):
    monkeypatch.delenv("MAIL_PROVIDER", raising=False)
    s = MailSettings(mail_recipients="a@example.com", mail_retry_delay_sec=0)
    assert s.mail_provider == "console"
    assert isinstance(providers.make_provider(s), providers.ConsoleProvider)
    run_once(s, None, NOW)
    assert {r["provider"] for r in mail_rows(dbs.backend)} == {"console"}


def test_body_copies_stored_report_only(dbs):
    rec = Recorder()
    run_once(settings(mail_recipients="a@example.com"), rec, NOW)
    by_subject = {s: b for _, s, b in rec.sent}
    llm = by_subject[
        "[DejaFix][High] LAB-PC-07 - High CPU utilization (over 85% for 1m)"
    ]
    # 저장된 값 그대로: 요약·원인(확신도 문자)·확인할 수 없음·계획 티어
    assert "LAB-PC-07의 CPU 사용률이 최근 1시간 최대 96.1%" in llm
    assert "특정 프로세스의 CPU 과다 사용 (확신도: medium)" in llm
    assert "백업 작업 여부 · NOT_COLLECTED" in llm
    assert "메모리 사용률 · STALE" in llm
    assert "[C] 프로세스 강제 종료" in llm and "최고 티어 C" in llm
    assert "미리보기 — 실행되지 않음" in llm
    assert "2026-10-15 10:20:00 KST" in llm  # 장애 시작 01:20Z → KST
    assert "execute" not in llm and "실행했" not in llm
    fb = by_subject[
        "[DejaFix][Average] LAB-PC-08 - High memory utilization (>90% for 5m)"
    ]
    assert compose.FALLBACK_LABEL in fb
    assert "(저장된 원인 후보 없음)" in fb


def test_link_uses_app_base_url(dbs):
    rec = Recorder()
    run_once(
        settings(mail_recipients="a@example.com", app_base_url="http://demo:8080/"),
        rec,
        NOW,
    )
    assert any("http://demo:8080/incidents/1" in b for _, _, b in rec.sent)
    assert "TODO: 추후결정" in compose.incident_link(
        "http://<데모 호스트 PC IP>:8080", 1
    )


def test_nothing_when_no_reports_or_no_shared_db(env, helpers):
    init_backend_db(get_settings())
    rec = Recorder()
    assert run_once(settings(), rec, NOW) == 0  # shared.db 없음
    conn = sqlite3.connect(env.shared)
    conn.executescript(
        split_zones(helpers.schema.read_text(encoding="utf-8"))["shared"]
    )
    conn.close()
    assert run_once(settings(), rec, NOW) == 0  # 리포트 없음
    assert rec.sent == []


def test_smtp_errors_hide_secrets(monkeypatch):
    s = MailSettings(mail_from="", smtp_password="super-secret")
    with pytest.raises(providers.MailError, match="MAIL_FROM"):
        providers.SmtpProvider(s).send("a@example.com", "s", "b")

    class Boom:
        def __init__(self, *a, **k):
            raise OSError("auth failed for super-secret")

    monkeypatch.setattr(providers.smtplib, "SMTP", Boom)
    s = MailSettings(mail_from="from@example.com", smtp_password="super-secret")
    with pytest.raises(providers.MailError) as exc:
        providers.SmtpProvider(s).send("a@example.com", "s", "b")
    assert "super-secret" not in str(exc.value)


def test_start_and_stop_worker(dbs, monkeypatch):
    monkeypatch.setenv("MAIL_RECIPIENTS", "a@example.com")
    monkeypatch.setenv("MAIL_POLL_SEC", "0.05")
    app = SimpleNamespace(state=SimpleNamespace())

    async def scenario():
        task = start_mail_worker(app)
        assert app.state.mail_worker_task is task
        for _ in range(100):
            if len(mail_rows(dbs.backend)) == 2:
                break
            await asyncio.sleep(0.05)
        await stop_mail_worker(app)
        assert task.cancelled() and app.state.mail_worker_task is None

    asyncio.run(scenario())
    assert len(mail_rows(dbs.backend)) == 2


def test_lifespan_starts_and_stops_worker(make_client):
    """#72: 백엔드 기동 시 메일 워커가 뜨고, 종료 시 태스크가 정리된다."""
    client = make_client()
    task = client.app.state.mail_worker_task
    assert task is not None and not task.done()
    client.__exit__(None, None, None)
    assert client.app.state.mail_worker_task is None
    assert task.done()
