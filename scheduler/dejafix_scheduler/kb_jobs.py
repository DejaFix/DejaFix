"""RAG 재색인 주기 작업 (NFR-RAG-003, 결정 017, Issue #159) — [이후].

- kb_reindex: 매일 03:00 KST(= 18:00 UTC) 전체 색인
- kb_notes: KB_NOTES_SEC(기본 300초)마다 해결 메모만 부분 색인
- KB_DB_PATH 가 비어 있으면 아무것도 하지 않는다(기존 poll_problems 동작 그대로).
- 색인은 별도 스레드 하나에서 돈다. 임베딩이 오래 걸리거나 실패해도 poll_problems 주기를 막지 않는다.
- 결과는 scheduler_jobs 의 job 행(kb_reindex·kb_notes)에만 남긴다. knowledge.db 작성자는 libs/kb 색인기.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shared_db import connect

from .poller import iso, upsert_job, utcnow

log = logging.getLogger("scheduler.kb")

JOB_FULL = "kb_reindex"
JOB_NOTES = "kb_notes"
NOTE_TYPE = "resolution_note"
FULL_HOUR_UTC = 18  # 03:00 KST

IndexFn = Callable[[set[str] | None], dict[str, Any]]


def _int(value: str | None, default: int, minimum: int) -> int:
    try:
        v = int(value) if value not in (None, "") else default
    except ValueError:
        v = default
    return max(minimum, v)


@dataclass(frozen=True)
class KbJobConfig:
    notes_sec: int
    retry_sec: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> KbJobConfig | None:
        """KB_DB_PATH 가 비어 있으면 None(작업 끔)."""
        e = os.environ if env is None else env
        if not (e.get("KB_DB_PATH") or "").strip():
            return None
        return cls(
            notes_sec=_int(e.get("KB_NOTES_SEC"), 300, 60),
            retry_sec=_int(e.get("KB_RETRY_SEC"), 300, 60),
        )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def last_full_slot(now: datetime) -> datetime:
    """now 이전(포함)의 가장 최근 03:00 KST 시각(UTC)."""
    slot = now.astimezone(UTC).replace(
        hour=FULL_HOUR_UTC, minute=0, second=0, microsecond=0
    )
    return slot if slot <= now else slot - timedelta(days=1)


def _job_row(
    conn: sqlite3.Connection, job: str
) -> tuple[datetime | None, datetime | None]:
    row = conn.execute(
        "SELECT last_run_at, last_ok_at FROM scheduler_jobs WHERE job = ?", (job,)
    ).fetchone()
    if row is None:
        return None, None
    return _parse(row[0]), _parse(row[1])


def due_jobs(conn: sqlite3.Connection, cfg: KbJobConfig, now: datetime) -> list[str]:
    """지금 돌릴 작업. 전체 색인이 우선이고, 같은 회차에 메모 색인은 하지 않는다(전체에 포함)."""
    last_run, last_ok = _job_row(conn, JOB_FULL)
    slot = last_full_slot(now)
    ran_ok_this_slot = last_ok is not None and last_ok >= slot
    waited = last_run is None or now - last_run >= timedelta(seconds=cfg.retry_sec)
    if not ran_ok_this_slot and (last_run is None or last_run < slot or waited):
        return [JOB_FULL]
    n_run, _ = _job_row(conn, JOB_NOTES)
    if n_run is None or now - n_run >= timedelta(seconds=cfg.notes_sec):
        return [JOB_NOTES]
    return []


def _summary(result: dict[str, Any]) -> str:
    idx = result.get("index") or {}
    parts = [f"{k}={v}" for k, v in idx.items() if isinstance(v, int)]
    parts.append(f"embedded={result.get('embedded_now', 0)}")
    if result.get("embed_error"):
        parts.append(f"embed_error={str(result['embed_error'])[:120]}")
    return " ".join(parts)[:200]


def run_job(
    conn: sqlite3.Connection, job: str, index_fn: IndexFn, now: datetime | None = None
) -> bool:
    """작업 1회. 예외로 죽지 않고 결과를 scheduler_jobs 에 남긴다."""
    stamp = iso(now or utcnow())
    only = {NOTE_TYPE} if job == JOB_NOTES else None
    try:
        result = index_fn(only)
        upsert_job(conn, job, stamp, True, _summary(result))
        log.info("%s ok %s", job, _summary(result))
        return True
    except Exception as exc:  # 다음 주기 재시도
        message = f"{type(exc).__name__}: {str(exc)[:200]}"
        upsert_job(conn, job, stamp, False, message)
        log.error("%s 실패: %s", job, message)
        return False


def default_index_fn() -> IndexFn:
    from dejafix_kb.config import KbSettings
    from dejafix_kb.indexer import run_index

    def _run(only: set[str] | None) -> dict[str, Any]:
        return run_index(KbSettings.from_env(), only_types=only)

    return _run


class KbRunner:
    """메인 루프가 tick() 을 부르면, 돌 차례인 작업을 별도 스레드 하나에서 돌린다."""

    def __init__(
        self,
        shared_db_path: str | Path,
        cfg: KbJobConfig,
        index_fn: IndexFn | None = None,
    ) -> None:
        self.shared_db_path = shared_db_path
        self.cfg = cfg
        self.index_fn = index_fn or default_index_fn()
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tick(self, now: datetime | None = None) -> str | None:
        """돌 차례면 작업을 시작하고 그 이름을, 아니면(또는 이미 도는 중이면) None 을 돌려준다."""
        if self.busy:
            return None
        now = now or utcnow()
        conn = connect(self.shared_db_path)
        try:
            jobs = due_jobs(conn, self.cfg, now)
        finally:
            conn.close()
        if not jobs:
            return None
        job = jobs[0]
        self._thread = threading.Thread(
            target=self._work, args=(job,), name=f"kb-{job}", daemon=True
        )
        self._thread.start()
        return job

    def _work(self, job: str) -> None:
        conn = connect(self.shared_db_path)
        try:
            run_job(conn, job, self.index_fn)
        finally:
            conn.close()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
