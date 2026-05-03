import os
import threading
import queue
import logging
from datetime import datetime, timedelta

from app.services.job_repository import JobRepository
from app.services.notifier import Notifier

logger = logging.getLogger('print_server')


class QueueManager:
    def __init__(self, config, broadcaster=None, db_path=None, notifier: Notifier | None = None):
        self.config = config
        self._broadcaster = broadcaster
        self._notifier = notifier
        self._print_engine = None
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._workers = []
        self._stop_evt = threading.Event()
        self._cancelled_ids = set()
        self._cancelled_lock = threading.Lock()
        self._word_lock = threading.Lock()
        self._excel_lock = threading.Lock()
        self._ppt_lock = threading.Lock()

        self._repo = JobRepository(db_path)

    def _is_cancelled(self, job_id):
        with self._cancelled_lock:
            return job_id in self._cancelled_ids

    def _mark_cancelled(self, job_id):
        with self._cancelled_lock:
            self._cancelled_ids.add(job_id)

    def _clear_cancelled(self, job_id):
        with self._cancelled_lock:
            self._cancelled_ids.discard(job_id)

    def add_job(self, filename, filepath, file_size=0, file_type='',
                duplex=None, color=None, copies=None, paper_size=None, printer_name=None,
                source='api'):
        job_id = self._repo.add_job(filename, filepath, file_size, file_type,
                                    duplex=duplex, color=color, copies=copies,
                                    paper_size=paper_size, printer_name=printer_name,
                                    source=source)
        self._queue.put(job_id)
        logger.info(f'任务已入队: {job_id} - {filename}')
        return job_id

    def get_job(self, job_id):
        return self._repo.get_job(job_id)

    def update_status(self, job_id, status, error_message=None):
        self._repo.update_status(job_id, status, error_message)

    def get_jobs(self, status=None, search=None, limit=50, offset=0):
        return self._repo.get_jobs(status, search, limit, offset)

    def count_jobs(self, status=None, search=None):
        return self._repo.count_jobs(status, search)

    def get_jobs_by_status(self, status):
        return self._repo.get_jobs_by_status(status)

    def get_stats(self):
        return self._repo.get_stats()

    def get_printers(self):
        """获取 Windows 可用打印机列表"""
        try:
            import win32print
            printers = win32print.EnumPrinters(2)
            return [p[2] for p in printers]
        except Exception as e:
            logger.error(f'获取打印机列表失败: {e}')
            return []

    def word_lock(self):
        return self._word_lock

    def excel_lock(self):
        return self._excel_lock

    def ppt_lock(self):
        return self._ppt_lock

    def start_workers(self, print_engine):
        self._print_engine = print_engine
        self._stop_evt.clear()
        count = self.config.worker_count
        self._workers = []
        for i in range(count):
            worker = threading.Thread(target=self._worker_loop, args=(print_engine, i), daemon=False)
            worker.start()
            self._workers.append(worker)
        logger.info(f'启动 {count} 个工作线程')

        # 启动心跳检测定时器（每 30 秒执行一次）
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info('心跳检测线程已启动')

    def _heartbeat_loop(self):
        """每 30 秒执行一次 cleanup_old_jobs"""
        while not self._stop_evt.is_set():
            try:
                self.cleanup_old_jobs()
            except Exception as e:
                logger.error(f'心跳检测异常: {e}')
            self._stop_evt.wait(30)

    def stop_workers(self):
        self._stop_evt.set()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('工作线程已全部停止')

    def _worker_loop(self, print_engine, worker_id):
        import pythoncom
        pythoncom.CoInitialize()
        logger.info(f'工作线程 {worker_id} 已启动')
        while not self._stop_evt.is_set():
            try:
                job_id = self._queue.get(timeout=1)
                # Skip cancelled jobs silently
                if self._is_cancelled(job_id):
                    self._clear_cancelled(job_id)
                    self._queue.task_done()
                    continue
                self._process_job(job_id, print_engine, worker_id)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f'工作线程 {worker_id} 异常: {e}')
        pythoncom.CoUninitialize()
        logger.info(f'工作线程 {worker_id} 已停止')

    def _process_job(self, job_id, print_engine, worker_id):
        max_retries = self.config.get('auto_retry_count', 0)
        for attempt in range(max_retries + 1):
            job = self.get_job(job_id)
            if not job or self._is_cancelled(job_id):
                return
            success, error_msg = self._do_print(job_id, print_engine, worker_id, attempt)
            if success:
                return
            if attempt < max_retries and error_msg not in ('用户取消',):
                logger.info(f'任务 {job_id} 第 {attempt + 1}/{max_retries} 次重试')
                self.update_status(job_id, 'queued', f'重试 {attempt + 1}/{max_retries}')
                self._repo.increment_retry(job_id)
                continue
            break
        # Final failure — emit notification
        job = self.get_job(job_id)
        if job:
            self._notify_all('failed', job['filename'], source=job.get('source', 'api'), error=error_msg)

    def _do_print(self, job_id, print_engine, worker_id, attempt=0):
        import tempfile
        import shutil
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        job = self.get_job(job_id)
        if not job:
            return False, '任务不存在'

        if self._is_cancelled(job_id):
            self._clear_cancelled(job_id)
            return True, None

        if attempt == 0:
            logger.info(f'[{worker_id}] 开始打印: {job["filename"]}')
        else:
            logger.info(f'[{worker_id}] 第 {attempt} 次重试: {job["filename"]}')

        self.update_status(job_id, 'printing')

        original_path = job['filepath']
        temp_path = None

        try:
            suffix = os.path.splitext(job['filename'])[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copy2(original_path, tmp.name)
                temp_path = tmp.name

            timeout = self.config.get('job_timeout', 300)
            pool = ThreadPoolExecutor(max_workers=1)
            try:
                print_params = {
                    'printer_name': job.get('printer_name') or '',
                    'copies': job.get('copies') or 1,
                    'duplex': job.get('duplex'),
                    'color': job.get('color'),
                    'paper_size': job.get('paper_size') or '',
                }
                fut = pool.submit(
                    print_engine.print_file,
                    temp_path, job['file_type'], job_id, self._word_lock, print_params
                )

                # Determine lock for COM cancel detection
                lock = None
                if job.get('file_type') in ('.doc', '.docx'):
                    lock = self._word_lock
                elif job.get('file_type') in ('.xls', '.xlsx'):
                    lock = self._excel_lock
                elif job.get('file_type') in ('.ppt', '.pptx'):
                    lock = self._ppt_lock

                if lock:
                    # COM job — poll for cancel every 1s
                    while not self._stop_evt.is_set():
                        try:
                            success = fut.result(timeout=1)
                            break
                        except FuturesTimeout:
                            if self._is_cancelled(job_id):
                                logger.info(f'任务 {job_id} 已被取消，终止等待')
                                if self._print_engine:
                                    self._print_engine.cancel_active_job(job_id)
                                return True, None
                else:
                    success = fut.result(timeout=timeout)
            finally:
                pool.shutdown(wait=False)

            if self._is_cancelled(job_id):
                logger.info(f'任务 {job_id} 已被外部取消，跳过后续处理')
                self._clear_cancelled(job_id)
                return True, None

            if success:
                self.update_status(job_id, 'completed')
                logger.info(f'打印完成: {job["filename"]}')
                if self._broadcaster:
                    self._broadcaster.publish('job_status', {
                        'job_id': job_id,
                        'filename': job['filename'],
                        'status': 'completed',
                        'source': job.get('source', 'api'),
                        'ts': datetime.now().isoformat()
                    })
                self._notify_all('completed', job['filename'], source=job.get('source', 'api'))
                return True, None
            else:
                error_msg = '打印引擎返回失败'
                self.update_status(job_id, 'failed', error_msg)
                logger.error(f'打印失败: {job["filename"]}')
                if self._broadcaster:
                    self._broadcaster.publish('job_status', {
                        'job_id': job_id,
                        'filename': job['filename'],
                        'status': 'failed',
                        'error': error_msg,
                        'source': job.get('source', 'api'),
                        'ts': datetime.now().isoformat()
                    })
                return False, error_msg

        except FuturesTimeout:
            error_msg = f'打印超时 ({timeout}s)'
            self.update_status(job_id, 'failed', error_msg)
            logger.error(f'打印超时: {job["filename"]}')
            if self._broadcaster:
                self._broadcaster.publish('job_status', {
                    'job_id': job_id,
                    'filename': job['filename'],
                    'status': 'failed',
                    'error': error_msg,
                    'source': job.get('source', 'api'),
                    'ts': datetime.now().isoformat()
                })
            return False, error_msg

        except Exception as e:
            error_msg = str(e)
            self.update_status(job_id, 'failed', error_msg)
            logger.error(f'打印异常: {job["filename"]} - {error_msg}')
            if self._broadcaster:
                self._broadcaster.publish('job_status', {
                    'job_id': job_id,
                    'filename': job['filename'],
                    'status': 'failed',
                    'error': error_msg,
                    'source': job.get('source', 'api'),
                    'ts': datetime.now().isoformat()
                })
            return False, error_msg

        finally:
            # Only delete source file on success, not on failure (keep for retry)
            job_after = self.get_job(job_id)
            if job_after and job_after.get('status') == 'completed':
                try:
                    if os.path.exists(original_path):
                        os.remove(original_path)
                except Exception as e:
                    logger.warning(f'删除上传文件失败: {original_path} - {e}')
            if temp_path:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as e:
                    logger.warning(f'删除临时文件失败: {temp_path} - {e}')

    def cancel_job(self, job_id):
        job = self.get_job(job_id)
        if not job:
            return False, '任务不存在'
        if job['status'] not in ('queued', 'printing'):
            return False, '只能取消排队或打印中的任务'

        self._mark_cancelled(job_id)

        if job['status'] == 'queued':
            self.update_status(job_id, 'failed', '用户取消')
            if self._broadcaster:
                self._broadcaster.publish('job_status', {
                    'job_id': job_id, 'filename': job['filename'],
                    'status': 'failed', 'error': '用户取消',
                    'source': job.get('source', 'api')
                })
        else:
            # printing — send cancel to PrintEngine
            if self._print_engine:
                self._print_engine.cancel_active_job(job_id)
            self.update_status(job_id, 'failed', '用户取消')
            if self._broadcaster:
                self._broadcaster.publish('job_status', {
                    'job_id': job_id, 'filename': job['filename'],
                    'status': 'failed', 'error': '用户取消',
                    'source': job.get('source', 'api')
                })
            self._notify_all('cancelled', job['filename'], source=job.get('source', 'api'))

        # Delete job file
        try:
            filepath = job.get('filepath')
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.warning(f'删除取消任务文件失败: {e}')

        logger.info(f'任务已取消: {job_id}')
        return True, None

    def cancel_all_queued(self):
        jobs = self.get_jobs_by_status('queued')
        count = 0
        for job in jobs:
            if not self._is_cancelled(job['id']):
                self._mark_cancelled(job['id'])
                self.update_status(job['id'], 'failed', '用户取消')
                if self._broadcaster:
                    self._broadcaster.publish('job_status', {
                        'job_id': job['id'], 'filename': job['filename'],
                        'status': 'failed', 'error': '用户取消',
                        'source': job.get('source', 'api')
                    })
                try:
                    if job.get('filepath') and os.path.exists(job['filepath']):
                        os.remove(job['filepath'])
                except Exception as e:
                    logger.warning(f'删除取消任务文件失败: {e}')
                count += 1
        logger.info(f'批量取消完成: {count} 个任务')
        return count

    def retry_job(self, job_id):
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

    def _notify_all(self, event_type, filename, source='api', **kwargs):
        if source == 'ios':
            logger.debug(f'iOS 来源任务不发送通知: {filename}')
            return
        if not self._notifier:
            return
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            if event_type == 'completed':
                self._notifier.notify_job_completed(filename, time_str)
            elif event_type == 'failed':
                self._notifier.notify_job_failed(filename, kwargs.get('error', ''), time_str)
            elif event_type == 'cancelled':
                self._notifier.notify_job_cancelled(filename, time_str)
        except Exception:
            pass

    def cleanup_old_jobs(self):
        """清理过期任务 + 恢复卡住的 printing 任务"""
        # 清理过期历史记录（委托给 repo）
        retention_days = self.config.get('job_retention_days', 30)
        self._repo.cleanup_old_jobs(retention_days)

        # 心跳检测：找回卡在 printing 超过 5 分钟的任务，重新入队
        heartbeat = (datetime.now() - timedelta(minutes=5)).isoformat()
        stuck_jobs = self._repo.get_jobs_by_status('printing')
        stuck_ids = [j['id'] for j in stuck_jobs if j['created_at'] < heartbeat]
        if stuck_ids:
            for jid in stuck_ids:
                self._repo.update_status(jid, 'queued', '心跳恢复')
                self._queue.put(jid)
            logger.warning(f'心跳检测: 已将 {len(stuck_ids)} 个卡住的打印任务恢复为排队状态')

    def shutdown(self):
        self._stop_evt.set()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('队列管理器已关闭')
