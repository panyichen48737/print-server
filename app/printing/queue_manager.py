import os
import threading
import queue
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from app.printing.repository import JobRepository
from app.printing.worker import JobWorker
from app.services.notifier import Notifier


class QueueManager:
    def __init__(self, config: Any, repo: JobRepository, event_bus: Any = None,
                 notifier: Notifier | None = None) -> None:
        self.config = config
        self._event_bus = event_bus
        self._notifier = notifier
        self._print_engine = None
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._workers: list[JobWorker] = []
        self._stop_evt = threading.Event()
        self._cancelled_ids: set[str] = set()
        self._cancelled_lock = threading.Lock()
        self._word_lock = threading.Lock()
        self._excel_lock = threading.Lock()
        self._ppt_lock = threading.Lock()

        self._repo = repo
        self._heartbeat = None

    def _is_cancelled(self, job_id: str) -> bool:
        with self._cancelled_lock:
            return job_id in self._cancelled_ids

    def _mark_cancelled(self, job_id: str) -> None:
        with self._cancelled_lock:
            self._cancelled_ids.add(job_id)

    def _clear_cancelled(self, job_id: str) -> None:
        with self._cancelled_lock:
            self._cancelled_ids.discard(job_id)

    def add_job(self, filename: str, filepath: str, file_size: int = 0, file_type: str = '',
                duplex: int | None = None, color: int | None = None,
                copies: int | None = None, paper_size: str | None = None,
                printer_name: str | None = None,
                source: str = 'api') -> str:
        job_id = self._repo.add_job(filename, filepath, file_size, file_type,
                                    duplex=duplex, color=color, copies=copies,
                                    paper_size=paper_size, printer_name=printer_name,
                                    source=source)
        self._queue.put(job_id)
        logger.info(f'任务已入队: {job_id} - {filename}')
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        return self._repo.get_job(job_id)

    def update_status(self, job_id: str, status: str, error_message: str | None = None) -> None:
        self._repo.update_status(job_id, status, error_message)

    def get_jobs(self, status: str | None = None, search: str | None = None,
                 limit: int = 50, offset: int = 0) -> list[dict]:
        return self._repo.get_jobs(status, search, limit, offset)

    def count_jobs(self, status: str | None = None, search: str | None = None) -> int:
        return self._repo.count_jobs(status, search)

    def get_jobs_by_status(self, status: str) -> list[dict]:
        return self._repo.get_jobs_by_status(status)

    def get_stats(self) -> dict:
        return self._repo.get_stats()

    def word_lock(self) -> threading.Lock:
        return self._word_lock

    def excel_lock(self) -> threading.Lock:
        return self._excel_lock

    def ppt_lock(self) -> threading.Lock:
        return self._ppt_lock

    def start_workers(self, print_engine: Any) -> None:
        self._print_engine = print_engine
        self._stop_evt.clear()
        count = self.config.schema.worker_count
        self._workers = []
        for i in range(count):
            worker = JobWorker(i, self.config, self._queue, self._repo, self._event_bus,
                              self._stop_evt, self._cancelled_ids, self._cancelled_lock,
                              print_engine, self._notifier, self._word_lock)
            worker.start()
            self._workers.append(worker)
        logger.info(f'启动 {count} 个工作线程')

        from app.services.heartbeat import HeartbeatMonitor
        self._heartbeat = HeartbeatMonitor(
            interval=30,
            cleanup_fn=lambda: self.cleanup_old_jobs(),
            recover_stuck_fn=self._recover_stuck_jobs,
        )
        self._heartbeat.start()

    def stop_workers(self) -> None:
        self._stop_evt.set()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('工作线程已全部停止')

    def queue_size(self) -> int:
        return self._queue.qsize()

    def _emit_job_status(self, job: dict, status: str, error: str = '') -> None:
        if self._event_bus:
            self._event_bus.emit('job_status', {
                'job_id': job['id'], 'filename': job['filename'],
                'status': status, 'error': error,
                'source': job.get('source', 'api')
            })

    def _safe_remove(self, filepath: str | None, label: str = '') -> None:
        if not filepath:
            return
        try:
            os.remove(filepath)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.warning(f'删除{label}失败: {filepath} - {e}')

    def cancel_job(self, job_id: str) -> tuple[bool, str | None]:
        job = self.get_job(job_id)
        if not job:
            return False, '任务不存在'
        if job['status'] not in ('queued', 'printing'):
            return False, '只能取消排队或打印中的任务'

        self._mark_cancelled(job_id)

        if job['status'] == 'printing' and self._print_engine:
            self._print_engine.cancel_active_job(job_id)

        self.update_status(job_id, 'failed', '用户取消')
        self._emit_job_status(job, 'failed', '用户取消')

        source = job.get('source', 'api')
        if source != 'ios' and job['status'] == 'printing' and self._notifier:
            try:
                time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self._notifier.notify_job_cancelled(job['filename'], time_str)
            except Exception:
                pass

        self._safe_remove(job.get('filepath'), '取消任务文件')
        logger.info(f'任务已取消: {job_id}')
        return True, None

    def cancel_all_queued(self) -> int:
        jobs = self.get_jobs_by_status('queued')
        to_cancel = [j for j in jobs if not self._is_cancelled(j['id'])]
        if not to_cancel:
            return 0

        ids = [j['id'] for j in to_cancel]
        for jid in ids:
            self._mark_cancelled(jid)

        self._repo.batch_update_status(ids, 'failed', '用户取消')

        for job in to_cancel:
            self._emit_job_status(job, 'failed', '用户取消')
            self._safe_remove(job.get('filepath'), '取消任务文件')

        logger.info(f'批量取消完成: {len(to_cancel)} 个任务')
        return len(to_cancel)

    def retry_job(self, job_id: str) -> tuple[str | None, str | None]:
        """重试失败的任务"""
        job = self.get_job(job_id)
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

    def cleanup_old_jobs(self) -> None:
        """清理过期任务（心跳检测也调用此方法）"""
        retention_days = self.config.get('job_retention_days', 30)
        self._repo.cleanup_old_jobs(retention_days)

    def _recover_stuck_jobs(self) -> None:
        """恢复卡在 printing 超过 5 分钟的任务"""
        heartbeat = (datetime.now() - timedelta(minutes=5)).isoformat()
        stuck_jobs = self._repo.get_jobs_by_status('printing')
        stuck_ids = [j['id'] for j in stuck_jobs if j['created_at'] < heartbeat]
        if stuck_ids:
            for jid in stuck_ids:
                self._repo.update_status(jid, 'queued', '心跳恢复')
                self._queue.put(jid)
            logger.warning(f'心跳检测: 已将 {len(stuck_ids)} 个卡住的打印任务恢复为排队状态')

    def shutdown(self) -> None:
        self._stop_evt.set()
        if self._heartbeat:
            self._heartbeat.stop()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('队列管理器已关闭')
