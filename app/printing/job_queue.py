"""任务队列 — 入队、取消、状态管理、心跳恢复、工作线程"""

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from app.printing.repository import JobRecord, JobRepository


class JobQueue:
    """任务队列：入队/取消/重试/状态，持有待处理队列与已取消集合"""

    def __init__(self, repo: JobRepository, event_bus: Any = None, config: Any = None) -> None:
        self._repo = repo
        self._event_bus = event_bus
        self._config = config
        self._queue: queue.Queue = queue.Queue()
        self._cancelled_ids: set[str] = set()
        self._cancelled_lock = threading.Lock()
        self._queued_ids: set[str] = set()
        self._queued_ids_lock = threading.Lock()
        # Worker lifecycle (replaces WorkerPool/JobWorker/JobExecutor/RetryHandler)
        self._workers: list[threading.Thread] = []
        self._stop_evt = threading.Event()
        self._print_pool = ThreadPoolExecutor(max_workers=4)
        self._print_engine = None
        self._word_lock = None

    def set_print_engine(self, print_engine, word_lock=None):
        """设置打印引擎和 COM 互斥锁（bootstrap 后调用）"""
        self._print_engine = print_engine
        self._word_lock = word_lock

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

    def add_job(
        self,
        filename: str,
        filepath: str,
        file_size: int = 0,
        file_type: str = '',
        duplex: int | None = None,
        color: int | None = None,
        copies: int | None = None,
        paper_size: str | None = None,
        printer_name: str | None = None,
        source: str = 'api',
    ) -> str:
        job_id = self._repo.add_job(
            filename,
            filepath,
            file_size,
            file_type,
            duplex=duplex,
            color=color,
            copies=copies,
            paper_size=paper_size,
            printer_name=printer_name,
            source=source,
        )
        self._queue.put(job_id)
        with self._queued_ids_lock:
            self._queued_ids.add(job_id)
        logger.info(f'任务已入队: {job_id} - {filename}')
        return job_id

    def get_for_processing(self, timeout: float = 1.0) -> str | None:
        """阻塞获取下一个待处理任务 ID"""
        try:
            job_id = self._queue.get(timeout=timeout)
            with self._queued_ids_lock:
                self._queued_ids.discard(job_id)
            return job_id
        except queue.Empty:
            return None

    def task_done(self) -> None:
        self._queue.task_done()

    def queue_size(self) -> int:
        return self._queue.qsize()

    # ── 取消业务 ──

    def cancel_job(self, job_id: str, print_engine: Any = None) -> tuple[bool, str | None]:
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

    def retry_job(self, job_id: str) -> tuple[str | None, str | None]:
        job = self._repo.get_job(job_id)
        if not job:
            return None, '任务不存在'
        if job['status'] != 'failed':
            return None, '只能重试失败的任务'
        new_job_id = self.add_job(
            job['filename'],
            job['filepath'],
            job['file_size'],
            job['file_type'],
            duplex=job.get('duplex'),
            color=job.get('color'),
            copies=job.get('copies'),
            paper_size=job.get('paper_size'),
            printer_name=job.get('printer_name'),
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

        with self._queued_ids_lock:
            already_queued = self._queued_ids.copy()

        requeued = 0
        for jid in stuck_ids:
            if jid in already_queued:
                continue
            self._repo.update_status(jid, 'queued', '心跳恢复')
            self._queue.put(jid)
            with self._queued_ids_lock:
                self._queued_ids.add(jid)
            requeued += 1

        if requeued > 0:
            logger.warning(f'心跳检测: 已将 {requeued} 个卡住的打印任务恢复为排队状态')

    # ── Worker lifecycle (replaces WorkerPool/JobWorker/JobExecutor/RetryHandler) ──

    def start(self, count: int = 2) -> None:
        """Start worker threads that process jobs from the queue."""
        self._stop_evt.clear()
        self._workers = []
        for i in range(count):
            t = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            self._workers.append(t)

    def stop(self, timeout: float = 15) -> None:
        """Signal all workers to stop and wait for them."""
        self._stop_evt.set()
        for t in self._workers:
            t.join(timeout=timeout / max(len(self._workers), 1))
        self._workers.clear()
        self._print_pool.shutdown(wait=False)

    def running_workers(self) -> int:
        return sum(1 for t in self._workers if t.is_alive())

    def _worker_loop(self, worker_id: int) -> None:
        """Worker thread main loop — CoInitialize, process jobs, CoUninitialize."""
        import pythoncom

        pythoncom.CoInitialize()
        try:
            while not self._stop_evt.is_set():
                try:
                    job_id = self.get_for_processing(timeout=1)
                    if job_id is None:
                        continue
                    if self.is_cancelled(job_id):
                        self.clear_cancelled(job_id)
                        self.task_done()
                        continue
                    self._execute_with_retry(job_id, worker_id)
                    self.task_done()
                except Exception:
                    logger.exception(f'工作线程 {worker_id} 异常')
        finally:
            pythoncom.CoUninitialize()

    def _execute_with_retry(self, job_id: str, worker_id: int) -> None:
        """Execute a job with optional retries."""
        max_retries = self._config.get('auto_retry_count', 0) if self._config else 0
        for attempt in range(max_retries + 1):
            result = self._execute_job(job_id, worker_id, attempt)
            if result == 'completed':
                return
            if attempt < max_retries and result not in ('cancelled',):
                logger.info(f'任务 {job_id} 第 {attempt + 1}/{max_retries} 次重试')
                self._repo.update_status(job_id, 'queued', f'重试 {attempt + 1}/{max_retries}')
                self._repo.increment_retry(job_id)
                continue
            break

    def _execute_job(self, job_id: str, worker_id: int, attempt: int = 0) -> str:
        """Execute a single print job. Returns 'completed', 'failed', 'timeout', or 'cancelled'."""
        job = self._repo.get_job(job_id)
        if not job or self.is_cancelled(job_id):
            return 'cancelled'

        if not self._print_engine:
            logger.error(f'打印引擎未初始化，无法打印: {job_id}')
            return 'failed'

        filename = job['filename']
        if attempt == 0:
            logger.info(f'[{worker_id}] 开始打印: {filename}')
        else:
            logger.info(f'[{worker_id}] 第 {attempt} 次重试: {filename}')

        self._update_and_broadcast(
            job_id, 'printing', filename=filename, source=job.get('source', 'api')
        )

        # Re-check cancel after status update
        if self.is_cancelled(job_id):
            self._repo.update_status(job_id, 'failed', '用户取消')
            self._update_and_broadcast(
                job_id, 'failed', '用户取消', filename, job.get('source', 'api')
            )
            return 'cancelled'

        original_path = job['filepath']
        try:
            from app.core.utils import temp_print_file

            with temp_print_file(original_path, filename) as temp_path:
                result = self._execute_print(temp_path, job, job_id)
                return self._finalize_job(job_id, job, original_path, result)
        except Exception as e:
            error_msg = str(e)
            self._update_and_broadcast(
                job_id, 'failed', error_msg, filename, job.get('source', 'api')
            )
            logger.error(f'打印异常: {filename} - {error_msg}')
            return 'failed'

    def _execute_print(self, temp_path: str, job: Any, job_id: str) -> str:
        """Submit print job to engine with timeout, returns status string."""

        engine = self._print_engine
        if not engine:
            return 'failed'

        print_params = {
            'printer_name': job.get('printer_name')
            or (self._config.get('default_printer', '') if self._config else ''),
            'copies': job.get('copies')
            or (self._config.get('default_copies', 1) if self._config else 1),
            'duplex': job.get('duplex')
            if job.get('duplex') is not None
            else (self._config.get('default_duplex', False) if self._config else False),
            'color': job.get('color')
            if job.get('color') is not None
            else (self._config.get('default_color', True) if self._config else True),
            'paper_size': job.get('paper_size')
            or (self._config.get('paper_size', 'A4') if self._config else 'A4'),
        }
        self._validate_color_capability(print_params)
        timeout = self._config.get('job_timeout', 300) if self._config else 300
        deadline = time.monotonic() + timeout

        try:
            fut = self._print_pool.submit(
                engine.print_file,
                temp_path,
                job['file_type'],
                job_id,
                self._word_lock,
                print_params,
            )
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FuturesTimeout
                try:
                    success = fut.result(timeout=min(1.0, remaining))
                    return 'completed' if success else 'failed'
                except FuturesTimeout:
                    if self.is_cancelled(job_id):
                        engine.cancel_active_job(job_id)
                        return 'cancelled'
        except FuturesTimeout:
            return 'timeout'

    def _finalize_job(self, job_id: str, job: Any, original_path: str, result: str) -> str:
        """Handle job completion/failure/timeout finalization."""
        if result == 'cancelled':
            return 'cancelled'

        filename, source = job.get('filename', ''), job.get('source', 'api')

        if result == 'completed':
            self._update_and_broadcast(job_id, 'completed', filename=filename, source=source)
            logger.info(f'打印完成: {filename}')
            from app.core.utils import safe_remove

            safe_remove(original_path, '上传文件')
            return 'completed'
        if result == 'timeout':
            timeout_val = self._config.get('job_timeout', 300) if self._config else 300
            error_msg = f'打印超时 ({timeout_val}s)'
            self._update_and_broadcast(job_id, 'failed', error_msg, filename, source)
            logger.error(f'打印超时: {filename}')
            return 'timeout'
        error_msg = '打印引擎返回失败'
        self._update_and_broadcast(job_id, 'failed', error_msg, filename, source)
        logger.error(f'打印失败: {filename}')
        return 'failed'

    def _update_and_broadcast(
        self,
        job_id: str,
        status: str,
        error_message: str | None = None,
        filename: str = '',
        source: str = 'api',
    ) -> None:
        """Update job status in DB and broadcast event."""
        self._repo.update_status(job_id, status, error_message)
        if self._event_bus:
            data = {
                'job_id': job_id,
                'filename': filename,
                'status': status,
                'source': source,
                'ts': datetime.now().isoformat(),
            }
            if error_message:
                data['error'] = error_message
            self._event_bus.publish('job_status', data)

    def _validate_color_capability(self, print_params: dict) -> None:
        """Check printer color capability, fallback to B&W if unsupported."""
        printer = print_params.get('printer_name', '')
        if not printer or print_params.get('color') is None:
            return
        try:
            import win32print

            dc_colordevice = 23
            color_raw = win32print.DeviceCapabilities(printer, None, dc_colordevice, None)
            if color_raw and color_raw[0] == 0 and print_params['color']:
                print_params['color'] = False
        except Exception:
            pass

    # ── 内部方法 ──

    def _emit_job_status(self, job: JobRecord, status: str, error: str = '') -> None:
        if self._event_bus:
            self._event_bus.publish(
                'job_status',
                {
                    'job_id': job['id'],
                    'filename': job['filename'],
                    'status': status,
                    'source': job.get('source', 'api'),
                    'error': error,
                    'ts': datetime.now().isoformat(),
                },
            )
