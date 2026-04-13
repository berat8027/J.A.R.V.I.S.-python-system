"""
tools/scheduler.py
──────────────────
Background task scheduler for JARVIS.
Uses the `schedule` library for simple recurring jobs.

Examples of scheduled tasks:
- Daily system health report
- Reminder announcements
- Periodic memory cleanup
"""

from __future__ import annotations
import threading
import time
from typing import Callable

import schedule
from loguru import logger


class TaskScheduler:

    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None
        self._jobs: list[dict] = []

    def add_daily(self, at_time: str, fn: Callable,
                  label: str = "") -> None:
        """Schedule fn() every day at HH:MM."""
        schedule.every().day.at(at_time).do(fn)
        self._jobs.append({"label": label or str(fn), "time": at_time})
        logger.info("Scheduled daily job '{}' at {}", label, at_time)

    def add_interval(self, seconds: int, fn: Callable,
                     label: str = "") -> None:
        """Schedule fn() every N seconds."""
        schedule.every(seconds).seconds.do(fn)
        self._jobs.append({"label": label or str(fn), "interval_s": seconds})
        logger.info("Scheduled interval job '{}' every {}s", label, seconds)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("TaskScheduler started with {} job(s)", len(self._jobs))

    def stop(self) -> None:
        self._running = False
        schedule.clear()

    def _loop(self) -> None:
        while self._running:
            schedule.run_pending()
            time.sleep(1)

    def list_jobs(self) -> list[dict]:
        return list(self._jobs)
