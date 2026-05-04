"""工作线程池 — 管理 JobWorker 生命周期"""
import threading
from typing import Any, Optional

from loguru import logger

from app.printing.job_queue import JobQueue
from app.printing.repository import JobRepository
from app.printing.worker import JobWorker


class WorkerPool:
    """工作线程池：启动/停止 Worker"""

    def __init__(self, config: Any, event_bus: Any = None,
                 word_lock: Optional[threading.Lock] = None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._word_lock = word_lock
        self._workers: list[JobWorker] = []
        self._stop_evt = threading.Event()

    def start(self, print_engine: Any, repo: JobRepository, job_queue: JobQueue) -> None:
        self._stop_evt.clear()
        count = self._config.schema.worker_count
        self._workers = []
        for i in range(count):
            worker = JobWorker(
                i, self._config, job_queue, repo, self._event_bus,
                self._stop_evt, print_engine, self._word_lock,
            )
            worker.start()
            self._workers.append(worker)
        logger.info(f'启动 {count} 个工作线程')

    def stop(self) -> None:
        self._stop_evt.set()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('工作线程已全部停止')
