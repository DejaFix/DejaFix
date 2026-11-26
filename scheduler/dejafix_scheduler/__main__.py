"""실행: uv run --package scheduler python -m scheduler"""

from __future__ import annotations

import logging
import threading

from shared_db import open_db

from .config import Settings
from .kb_jobs import KbJobConfig, KbRunner
from .migrate import migrate
from .poller import Scope, poll_once
from .source import CompanySources, make_source

log = logging.getLogger("scheduler")


def run(
    settings: Settings,
    stop: threading.Event | None = None,
    max_cycles: int | None = None,
    kb: KbRunner | None = None,
) -> int:
    """기동 시 shared 스키마를 멱등 적용하고 poll_sec 마다 한 주기씩 돈다. 돈 주기 수를 돌려준다.

    KB_DB_PATH 가 있으면 매 주기 끝에 RAG 재색인 차례를 확인한다(별도 스레드, [이후] #159).
    """
    stop = stop or threading.Event()
    conn = open_db(settings.shared_db_path, "shared")
    companies: CompanySources | None = None
    source = None
    if settings.default_company_id:
        # 결정 019: 회사마다 그 회사 Zabbix 로 폴링. 기동 때 Scheduler 몫 표를 한 번 이관한다
        companies = CompanySources(
            settings.default_company_id, settings.zabbix_mock, settings.mock_file
        )
        migrate(conn, settings.default_company_id, companies.migration_conn_id())
    else:
        source = make_source(settings.zabbix_mock, settings.mock_file)
    if kb is None:
        cfg = KbJobConfig.from_env()
        kb = KbRunner(settings.shared_db_path, cfg) if cfg else None
    log.info(
        "scheduler 시작 db=%s poll=%ds mock=%s",
        settings.shared_db_path,
        settings.poll_sec,
        settings.zabbix_mock,
    )
    cycles = 0
    try:
        while not stop.is_set():
            if companies is None:
                poll_once(conn, source)
            else:
                for company, conn_id in companies.scopes():
                    # 한 회사 실패는 그 회사 scheduler_jobs 에만 남고 다른 회사는 계속 돈다
                    poll_once(
                        conn, companies.source(company), scope=Scope(company, conn_id)
                    )
            if kb is not None:
                try:
                    kb.tick()
                except Exception as exc:  # 재색인 문제로 수집 루프가 멈추면 안 된다
                    log.error("kb 작업 확인 실패: %s", exc)
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            stop.wait(settings.poll_sec)
    finally:
        conn.close()
        if kb is not None:
            kb.join(timeout=5)
    return cycles


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        run(Settings.from_env())
    except KeyboardInterrupt:
        log.info("scheduler 종료")


if __name__ == "__main__":
    main()
