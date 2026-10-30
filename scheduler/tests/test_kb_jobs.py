"""RAG 재색인 주기 작업 (NFR-RAG-003, Issue #159) — libs/kb 색인 함수는 가짜로 바꿔 끼운다."""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from shared_db import open_db

from dejafix_scheduler.__main__ import run
from dejafix_scheduler.config import Settings
from dejafix_scheduler.kb_jobs import (
    JOB_FULL,
    JOB_NOTES,
    NOTE_TYPE,
    KbJobConfig,
    KbRunner,
    due_jobs,
    last_full_slot,
    run_job,
)
from dejafix_scheduler.poller import JOB, iso, upsert_job

CFG = KbJobConfig(notes_sec=300, retry_sec=300)
# 2026-10-16 19:00 UTC = 10/17 04:00 KST (오늘 03:00 KST 슬롯 = 10/16 18:00 UTC 이후)
AFTER_SLOT = datetime(2026, 10, 16, 19, 0, 0, tzinfo=UTC)
SLOT = datetime(2026, 10, 16, 18, 0, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "shared.db"
    c = open_db(path, "shared")
    yield path, c
    c.close()


def job_row(conn, job):
    return conn.execute(
        "SELECT last_run_at, last_ok_at, status, message FROM scheduler_jobs WHERE job=?",
        (job,),
    ).fetchone()


def test_disabled_when_kb_db_path_empty():
    assert KbJobConfig.from_env({}) is None
    assert KbJobConfig.from_env({"KB_DB_PATH": "  "}) is None
    cfg = KbJobConfig.from_env({"KB_DB_PATH": "data/knowledge.db"})
    assert cfg == KbJobConfig(notes_sec=300, retry_sec=300)
    # 너무 짧은 주기는 60초로 막는다(임베딩 429·비용)
    assert (
        KbJobConfig.from_env({"KB_DB_PATH": "x", "KB_NOTES_SEC": "5"}).notes_sec == 60
    )


def test_run_without_kb_leaves_only_poll_problems(db, monkeypatch, tmp_path):
    monkeypatch.delenv("KB_DB_PATH", raising=False)
    path, conn = db
    settings = Settings.from_env({"SHARED_DB_PATH": str(path), "ZABBIX_MOCK": "true"})
    assert run(settings, max_cycles=1) == 1
    jobs = [r[0] for r in conn.execute("SELECT job FROM scheduler_jobs")]
    assert jobs == [JOB]


def test_full_slot_is_0300_kst():
    assert last_full_slot(AFTER_SLOT) == SLOT
    # 18:00 UTC 전이면 전날 슬롯
    assert last_full_slot(SLOT - timedelta(minutes=1)) == SLOT - timedelta(days=1)
    assert last_full_slot(SLOT) == SLOT


def test_due_full_first_then_notes(db):
    _, conn = db
    # 처음엔 전체 색인부터
    assert due_jobs(conn, CFG, AFTER_SLOT) == [JOB_FULL]
    upsert_job(conn, JOB_FULL, iso(AFTER_SLOT), True, None)
    # 이번 슬롯에 성공했으면 전체는 다시 안 돌고, 메모 색인 차례
    assert due_jobs(conn, CFG, AFTER_SLOT + timedelta(seconds=1)) == [JOB_NOTES]
    upsert_job(conn, JOB_NOTES, iso(AFTER_SLOT), True, None)
    assert due_jobs(conn, CFG, AFTER_SLOT + timedelta(seconds=299)) == []
    assert due_jobs(conn, CFG, AFTER_SLOT + timedelta(seconds=300)) == [JOB_NOTES]
    # 다음 날 03:00 KST 가 지나면 다시 전체
    assert due_jobs(conn, CFG, AFTER_SLOT + timedelta(days=1)) == [JOB_FULL]


def test_failed_full_retries_after_retry_sec(db):
    _, conn = db
    upsert_job(conn, JOB_FULL, iso(AFTER_SLOT), False, "EmbedError")
    upsert_job(conn, JOB_NOTES, iso(AFTER_SLOT), True, None)
    # 실패 직후 30초 주기마다 다시 두드리지 않는다
    assert due_jobs(conn, CFG, AFTER_SLOT + timedelta(seconds=60)) == []
    assert due_jobs(conn, CFG, AFTER_SLOT + timedelta(seconds=300)) == [JOB_FULL]


def test_run_job_records_ok_and_partial_types(db):
    _, conn = db
    calls = []

    def fake(only):
        calls.append(only)
        return {"index": {"added": 2, "updated": 0, "removed": 0}, "embedded_now": 1}

    assert run_job(conn, JOB_NOTES, fake, now=AFTER_SLOT)
    assert run_job(conn, JOB_FULL, fake, now=AFTER_SLOT)
    assert calls == [{NOTE_TYPE}, None]  # 메모는 부분 색인, 전체는 전부
    last_run, last_ok, status, message = job_row(conn, JOB_FULL)
    assert (last_run, last_ok, status) == (iso(AFTER_SLOT), iso(AFTER_SLOT), "ok")
    assert "added=2" in message and "embedded=1" in message


def test_run_job_failure_keeps_last_ok_and_does_not_raise(db):
    _, conn = db
    upsert_job(conn, JOB_FULL, iso(SLOT), True, None)

    def boom(only):
        raise RuntimeError("knowledge.db locked")

    assert run_job(conn, JOB_FULL, boom, now=AFTER_SLOT) is False
    last_run, last_ok, status, message = job_row(conn, JOB_FULL)
    assert last_run == iso(AFTER_SLOT)
    assert last_ok == iso(SLOT)  # 지난 성공 시각 유지
    assert status == "error" and message.startswith("RuntimeError")


def test_slow_index_does_not_block_poll_loop(db, monkeypatch):
    """색인이 끝나지 않아도 poll_problems 주기는 계속 돈다(별도 스레드)."""
    monkeypatch.delenv("KB_DB_PATH", raising=False)
    path, conn = db
    started, release = threading.Event(), threading.Event()

    def slow(only):
        started.set()
        release.wait(5)
        return {"index": {}}

    runner = KbRunner(path, CFG, index_fn=slow)
    settings = Settings.from_env({"SHARED_DB_PATH": str(path), "ZABBIX_MOCK": "true"})
    stop = threading.Event()
    cycles = run(settings, stop=stop, max_cycles=2, kb=runner)
    assert cycles == 2
    assert started.is_set() and runner.busy  # 색인은 아직 도는 중
    assert runner.tick() is None  # 도는 동안 새 작업을 겹쳐 시작하지 않음
    release.set()
    runner.join(5)
    assert job_row(conn, JOB_FULL)[2] == "ok"
    assert job_row(conn, JOB)[2] == "ok"
