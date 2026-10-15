"""실행: uv run --package scheduler python -m scheduler"""

from __future__ import annotations

import logging
import threading

from shared_db import open_db

from .config import Settings
from .poller import poll_once
from .source import make_source

log = logging.getLogger("scheduler")


def run(
    settings: Settings,
    stop: threading.Event | None = None,
    max_cycles: int | None = None,
) -> int:
    """기동 시 shared 스키마를 멱등 적용하고 poll_sec 마다 한 주기씩 돈다. 돈 주기 수를 돌려준다."""
    stop = stop or threading.Event()
    conn = open_db(settings.shared_db_path, "shared")
    source = make_source(settings.zabbix_mock, settings.mock_file)
    log.info(
        "scheduler 시작 db=%s poll=%ds mock=%s",
        settings.shared_db_path,
        settings.poll_sec,
        settings.zabbix_mock,
    )
    cycles = 0
    try:
        while not stop.is_set():
            poll_once(conn, source)
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            stop.wait(settings.poll_sec)
    finally:
        conn.close()
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
