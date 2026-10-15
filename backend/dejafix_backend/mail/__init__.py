"""메일 워커 (T38·T39). main.py lifespan 에서 start_mail_worker(app) / stop_mail_worker(app)."""

from .worker import run_once, start_mail_worker, stop_mail_worker

__all__ = ["run_once", "start_mail_worker", "stop_mail_worker"]
