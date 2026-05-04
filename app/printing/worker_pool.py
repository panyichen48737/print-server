"""工作线程池 — 使用 ThreadPoolExecutor 管理线程生命周期"""
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from loguru import logger

from app.printing.job_queue import JobQueue
from app.printing.repository import JobRepository
from app.printing.worker import JobWorker


class WorkerPool:
    """工作线程池：基于 ThreadPoolExecutor 的启动/停止"""

    def __init__(self, config: Any, event_bus: Any = None,
                 word_lock: Optional[threading.Lock] = None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._word_lock = word_lock
        self._executor: ThreadPoolExecutor | None = None
        self._futures: list = []
        self._stop_evt = threading.Event()

    def start(self, print_engine: Any, repo: JobRepository, job_queue: JobQueue) -> None:
        self._stop_evt.clear()
        count = self._config.get('worker_count', 2)
        self._executor = ThreadPoolExecutor(max_workers=count)
        self._futures = []
        for i in range(count):
            worker = JobWorker(
                i, self._config, job_queue, repo, self._event_bus,
                self._stop_evt, print_engine, self._word_lock,
            )
            self._futures.append(self._executor.submit(worker.run))
        logger.info(f'启动 {count} 个工作线程')

    def stop(self) -> None:
        self._stop_evt.set()
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None
        self._futures = []
        logger.info('工作线程已全部停止')
