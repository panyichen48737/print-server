"""工作线程与任务执行器"""

import contextlib
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from loguru import logger

from app.core.utils import safe_remove


class JobExecutor:
    """封装单个打印任务的执行流程（临时文件、取消检测、超时）"""

    def __init__(
        self,
        config: Any,
        event_bus: Any,
        repo,
        print_engine: Any,
        get_cancelled_fn,
        word_lock: threading.Lock,
    ):
        self.config = config
        self._event_bus = event_bus
        self._repo = repo
        self._print_engine = print_engine
        self._is_cancelled = get_cancelled_fn
        self._word_lock = word_lock
        self._pool = ThreadPoolExecutor(max_workers=1)

    def shutdown(self):
        with contextlib.suppress(Exception):
            self._pool.shutdown(wait=False)

    def execute(self, job_id: str, worker_id: int, attempt: int = 0) -> tuple[bool, str | None]:
        """执行单个打印任务"""
        job = self._repo.get_job(job_id)
        if not job or self._is_cancelled(job_id):
            return True, None

        filename = job['filename']
        prefix = f'[{worker_id}]'
        if attempt == 0:
            logger.info(f'{prefix} 开始打印: {filename}')
        else:
            logger.info(f'{prefix} 第 {attempt} 次重试: {filename}')

        self._update_and_broadcast(
            job_id, 'printing', filename=filename, source=job.get('source', 'api')
        )

        # Re-check cancel AFTER status update (closes the race window)
        if self._is_cancelled(job_id):
            self._repo.update_status(job_id, 'failed', '用户取消')
            self._update_and_broadcast(
                job_id, 'failed', '用户取消', filename, job.get('source', 'api')
            )
            return True, None

        original_path = job['filepath']
        try:
            from app.core.utils import temp_print_file

            with temp_print_file(original_path, filename) as temp_path:
                result = self._execute_print(temp_path, job, job_id)
                return self._finalize(job_id, original_path, temp_path, result, job)
        except Exception as e:
            error_msg = str(e)
            self._update_and_broadcast(
                job_id, 'failed', error_msg, filename, job.get('source', 'api')
            )
            logger.error(f'打印异常: {filename} - {error_msg}')
            return False, error_msg

    def _update_and_broadcast(self, job_id, status, error_message=None, filename='', source='api'):
        self._repo.update_status(job_id, status, error_message)
        if self._event_bus:
            data = {
                'job_id': job_id,
                'filename': filename,
                'status': status,
                'source': source,
                'ts': datetime.datetime.now().isoformat(),
            }
            if error_message:
                data['error'] = error_message
            self._event_bus.publish('job_status', data)

    def _execute_print(self, temp_path, job, job_id):
        print_params = {
            'printer_name': job.get('printer_name') or self.config.get('default_printer', ''),
            'copies': job.get('copies') or self.config.get('default_copies', 1),
            'duplex': job.get('duplex')
            if job.get('duplex') is not None
            else self.config.get('default_duplex', False),
            'color': job.get('color')
            if job.get('color') is not None
            else self.config.get('default_color', True),
            'paper_size': job.get('paper_size') or self.config.get('paper_size', 'A4'),
        }
        # 校验颜色与打印机能力匹配，不匹配时自动回退
        self._validate_color_capability(print_params)
        timeout = self.config.get('job_timeout', 300)
        deadline = time.monotonic() + timeout
        try:
            fut = self._pool.submit(
                self._print_engine.print_file,
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
                    if self._is_cancelled(job_id):
                        self._print_engine.cancel_active_job(job_id)
                        return 'cancelled'
        except FuturesTimeout:
            return 'timeout'

    def _finalize(self, job_id, original_path, _temp_path, result, job):
        if result == 'cancelled':
            return True, None

        filename, source = job.get('filename', ''), job.get('source', 'api')

        if result == 'completed':
            self._update_and_broadcast(job_id, 'completed', filename=filename, source=source)
            logger.info(f'打印完成: {filename}')
        elif result == 'timeout':
            error_msg = f'打印超时 ({self.config.get("job_timeout", 300)}s)'
            self._update_and_broadcast(job_id, 'failed', error_msg, filename, source)
            logger.error(f'打印超时: {filename}')
            return False, error_msg
        else:
            error_msg = '打印引擎返回失败'
            self._update_and_broadcast(job_id, 'failed', error_msg, filename, source)
            logger.error(f'打印失败: {filename}')
            return False, error_msg

        safe_remove(original_path, '上传文件')

        return True, None

    def _validate_color_capability(self, print_params: dict) -> None:
        """检查打印机颜色能力，不匹配时自动回退到支持的模式"""
        printer = print_params.get('printer_name', '')
        if not printer or print_params.get('color') is None:
            return
        try:
            import win32print

            dc_colordevice = 23
            color_raw = win32print.DeviceCapabilities(printer, None, dc_colordevice, None)
            if color_raw and color_raw[0] == 0 and print_params['color']:
                # 打印机不支持彩色，回退到黑白
                print_params['color'] = False
                logger.info(f'打印机 [{printer}] 不支持彩色，已自动切换为黑白')
        except Exception:
            pass


class JobWorker:
    """单个工作线程 — 从 JobQueue 取任务并委托给 JobExecutor"""

    def __init__(
        self, worker_id: int, config, job_queue, repo, event_bus, stop_evt, print_engine, word_lock
    ):
        self.worker_id = worker_id
        self._config = config
        self._job_queue = job_queue
        self._repo = repo
        self._event_bus = event_bus
        self._stop_evt = stop_evt
        self._executor = JobExecutor(
            config, event_bus, repo, print_engine, job_queue.is_cancelled, word_lock
        )

    def run(self):
        """由 ThreadPoolExecutor 调用，运行事件循环直到收到停止信号"""
        import pythoncom

        pythoncom.CoInitialize()
        try:
            logger.info(f'工作线程 {self.worker_id} 已启动')
            handler = RetryHandler(self._config, self._repo, self._executor)
            while not self._stop_evt.is_set():
                try:
                    job_id = self._job_queue.get_for_processing(timeout=1)
                    if job_id is None:
                        continue
                    if self._job_queue.is_cancelled(job_id):
                        self._job_queue.clear_cancelled(job_id)
                        self._job_queue.task_done()
                        continue
                    handler.run_with_retry(job_id, self.worker_id)
                    self._job_queue.task_done()
                except Exception as e:
                    logger.error(f'工作线程 {self.worker_id} 异常: {e}')
        finally:
            self._executor.shutdown()
            pythoncom.CoUninitialize()
            logger.info(f'工作线程 {self.worker_id} 已停止')


class RetryHandler:
    """封装任务重试逻辑"""

    def __init__(self, config, repo, executor: JobExecutor):
        self._config = config
        self._repo = repo
        self._executor = executor

    def run_with_retry(self, job_id: str, worker_id: int) -> None:
        max_retries = self._config.get('auto_retry_count', 0)
        job = self._repo.get_job(job_id)
        if not job:
            return
        for attempt in range(max_retries + 1):
            success, error_msg = self._executor.execute(job_id, worker_id, attempt)
            if success:
                return
            if attempt < max_retries and error_msg not in ('用户取消',):
                logger.info(f'任务 {job_id} 第 {attempt + 1}/{max_retries} 次重试')
                self._repo.update_status(job_id, 'queued', f'重试 {attempt + 1}/{max_retries}')
                self._repo.increment_retry(job_id)
                continue
            break
