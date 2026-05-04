"""工作线程池 — 管理 JobWorker 生命周期与 COM 锁，从 QueueManager 拆出的独立职责"""
import threading
from typing import Any, Optional

from loguru import logger

from app.printing.job_queue import JobQueue
from app.printing.repository import JobRepository
from app.printing.worker import JobWorker


class WorkerPool:
    """工作线程池：启动/停止 Worker、持有 COM 互斥锁"""

    def __init__(self, config: Any, event_bus: Any = None) -> None:
        self._config = config
        self._event_bus = event_bus
        self._word_lock = threading.Lock()
        self._excel_lock = threading.Lock()
        self._ppt_lock = threading.Lock()
        self._workers: list[JobWorker] = []
        self._stop_evt = threading.Event()
        self._heartbeat: Any = None

    # ── 锁 ──

    def word_lock(self) -> threading.Lock:
        return self._word_lock

    def excel_lock(self) -> threading.Lock:
        return self._excel_lock

    def ppt_lock(self) -> threading.Lock:
        return self._ppt_lock

    # ── 生命周期 ──

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

        from app.services.heartbeat import HeartbeatMonitor
        self._heartbeat = HeartbeatMonitor(
            interval=30,
            cleanup_fn=lambda: job_queue.cleanup_old_jobs(
                self._config.get('job_retention_days', 30)),
            recover_stuck_fn=job_queue.recover_stuck_jobs,
        )
        self._heartbeat.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._heartbeat:
            self._heartbeat.stop()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('工作线程已全部停止')

    def shutdown(self) -> None:
        self.stop()
