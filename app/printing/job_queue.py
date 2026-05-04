"""任务队列 — 入队、取消、状态管理、心跳恢复"""
import queue
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger

from app.printing.repository import JobRepository


class JobQueue:
    """任务队列：入队/取消/重试/状态，持有待处理队列与已取消集合"""

    def __init__(self, repo: JobRepository, event_bus: Any = None) -> None:
        self._repo = repo
        self._event_bus = event_bus
        self._queue: queue.Queue = queue.Queue()
        self._cancelled_ids: set[str] = set()
        self._cancelled_lock = threading.Lock()

    # ── 取消检测 ──

    def is_cancelled(self, job_id: str) -> bool:
        with self._cancelled_lock:
            return job_id in self._cancelled_ids

    def mark_cancelled(self, job_id: str) -> None:
        with self._cancelled_lock:
            self._cancelled_ids.add(job_id)

    def clear_cancelled(self, job_id: str) -> None:
        with self._cancelled_lock:
            self._cancelled_ids.discard(job_id)

    # ── 队列操作 ──

    def add_job(self, filename: str, filepath: str, file_size: int = 0, file_type: str = '',
                duplex: Optional[int] = None, color: Optional[int] = None,
                copies: Optional[int] = None, paper_size: Optional[str] = None,
                printer_name: Optional[str] = None, source: str = 'api') -> str:
        job_id = self._repo.add_job(filename, filepath, file_size, file_type,
                                    duplex=duplex, color=color, copies=copies,
                                    paper_size=paper_size, printer_name=printer_name,
                                    source=source)
        self._queue.put(job_id)
        logger.info(f'任务已入队: {job_id} - {filename}')
        return job_id

    def get_for_processing(self, timeout: float = 1.0) -> Optional[str]:
        """阻塞获取下一个待处理任务 ID"""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def task_done(self) -> None:
        self._queue.task_done()

    def queue_size(self) -> int:
        return self._queue.qsize()

    # ── 取消业务 ──

    def cancel_job(self, job_id: str, print_engine: Any = None) -> tuple[bool, Optional[str]]:
        job = self._repo.get_job(job_id)
        if not job:
            return False, '任务不存在'
        if job['status'] not in ('queued', 'printing'):
            return False, '只能取消排队或打印中的任务'

        self.mark_cancelled(job_id)

        if job['status'] == 'printing' and print_engine:
            print_engine.cancel_active_job(job_id)

        self._repo.update_status(job_id, 'failed', '用户取消')
        self._emit_job_status(job, 'failed', '用户取消')

        logger.info(f'任务已取消: {job_id}')
        return True, None

    def cancel_all_queued(self) -> int:
        jobs = self._repo.get_jobs_by_status('queued')
        to_cancel = [j for j in jobs if not self.is_cancelled(j['id'])]
        if not to_cancel:
            return 0

        ids = [j['id'] for j in to_cancel]
        for jid in ids:
            self.mark_cancelled(jid)

        self._repo.batch_update_status(ids, 'failed', '用户取消')

        for job in to_cancel:
            self._emit_job_status(job, 'failed', '用户取消')

        logger.info(f'批量取消完成: {len(to_cancel)} 个任务')
        return len(to_cancel)

    def retry_job(self, job_id: str) -> tuple[Optional[str], Optional[str]]:
        job = self._repo.get_job(job_id)
        if not job:
            return None, '任务不存在'
        if job['status'] != 'failed':
            return None, '只能重试失败的任务'
        new_job_id = self.add_job(
            job['filename'], job['filepath'],
            job['file_size'], job['file_type'],
            duplex=job.get('duplex'),
            color=job.get('color'),
            copies=job.get('copies'),
            paper_size=job.get('paper_size'),
            printer_name=job.get('printer_name')
        )
        logger.info(f'任务重试: {job_id} -> {new_job_id}')
        return new_job_id, None

    # ── 维护 ──

    def cleanup_old_jobs(self, retention_days: int = 30) -> None:
        self._repo.cleanup_old_jobs(retention_days)

    def recover_stuck_jobs(self) -> None:
        heartbeat = (datetime.now() - timedelta(minutes=5)).isoformat()
        stuck_jobs = self._repo.get_jobs_by_status('printing')
        stuck_ids = [j['id'] for j in stuck_jobs if j['created_at'] < heartbeat]
        if stuck_ids:
            for jid in stuck_ids:
                self._repo.update_status(jid, 'queued', '心跳恢复')
                self._queue.put(jid)
            logger.warning(f'心跳检测: 已将 {len(stuck_ids)} 个卡住的打印任务恢复为排队状态')

    # ── 内部方法 ──

    def _emit_job_status(self, job: dict, status: str, error: str = '') -> None:
        if self._event_bus:
            self._event_bus.publish('job_status', {
                'job_id': job['id'],
                'filename': job['filename'],
                'status': status,
                'source': job.get('source', 'api'),
                'error': error,
                'ts': datetime.now().isoformat(),
            })
