import os
import sqlite3
import threading
import uuid
import queue
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('print_server')


class QueueManager:
    def __init__(self, config, db_path=None):
        self.config = config
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._workers = []
        self._stop_evt = threading.Event()
        self._word_lock = threading.Lock()
        self._excel_lock = threading.Lock()
        self._ppt_lock = threading.Lock()

        if db_path is None:
            from app._paths import app_root, ensure_dir
            db_dir = ensure_dir(app_root(), 'jobs')
            db_path = os.path.join(db_dir, 'jobs.db')
        self.db_path = db_path

        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    file_type TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    error_message TEXT DEFAULT '',
                    printer_name TEXT DEFAULT '',
                    copies INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)')
            conn.commit()

    def add_job(self, filename, filepath, file_size=0, file_type=''):
        job_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT INTO jobs (id, filename, filepath, file_size, file_type, status) VALUES (?, ?, ?, ?, ?, ?)',
                (job_id, filename, filepath, file_size, file_type, 'queued')
            )
            conn.commit()
        self._queue.put(job_id)
        logger.info(f'任务已入队: {job_id} - {filename}')
        return job_id

    def get_job(self, job_id):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
            if row:
                return dict(row)
            return None

    def update_status(self, job_id, status, error_message=None):
        with sqlite3.connect(self.db_path) as conn:
            now = datetime.now().isoformat()
            if status in ('completed', 'failed'):
                conn.execute(
                    'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
                    (status, error_message or '', now, job_id)
                )
            else:
                conn.execute(
                    'UPDATE jobs SET status = ? WHERE id = ?',
                    (status, job_id)
                )
            conn.commit()

    def get_jobs(self, status=None, search=None, limit=50, offset=0):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = 'SELECT * FROM jobs WHERE 1=1'
            params = []
            if status:
                query += ' AND status = ?'
                params.append(status)
            if search:
                query += ' AND filename LIKE ?'
                params.append(f'%{search}%')
            query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def count_jobs(self, status=None, search=None):
        with sqlite3.connect(self.db_path) as conn:
            query = 'SELECT COUNT(*) FROM jobs WHERE 1=1'
            params = []
            if status:
                query += ' AND status = ?'
                params.append(status)
            if search:
                query += ' AND filename LIKE ?'
                params.append(f'%{search}%')
            return conn.execute(query, params).fetchone()[0]

    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            today = datetime.now().strftime('%Y-%m-%d')
            queued = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='queued'").fetchone()[0]
            printing = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='printing'").fetchone()[0]
            today_completed = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='completed' AND created_at >= ?", (today,)
            ).fetchone()[0]
            today_failed = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='failed' AND created_at >= ?", (today,)
            ).fetchone()[0]
            total = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
            success_total = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='completed'").fetchone()[0]
            failed_total = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='failed'").fetchone()[0]
            success_rate = (success_total / (success_total + failed_total) * 100) if (success_total + failed_total) > 0 else 100
            return {
                'queued': queued,
                'printing': printing,
                'today_completed': today_completed,
                'today_failed': today_failed,
                'total': total,
                'success_rate': success_rate
            }

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
            threading.Event().wait(30)

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
                self._process_job(job_id, print_engine, worker_id)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f'工作线程 {worker_id} 异常: {e}')
        pythoncom.CoUninitialize()
        logger.info(f'工作线程 {worker_id} 已停止')

    def _process_job(self, job_id, print_engine, worker_id):
        import tempfile
        import shutil
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        job = self.get_job(job_id)
        if not job:
            logger.warning(f'任务不存在: {job_id}')
            return

        logger.info(f'[{worker_id}] 开始打印: {job["filename"]}')
        self.update_status(job_id, 'printing')

        original_path = job['filepath']
        temp_path = None

        try:
            suffix = os.path.splitext(job['filename'])[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copy2(original_path, tmp.name)
                temp_path = tmp.name

            # 超时保护：用独立线程 + timeout 执行打印，防止 COM 调用卡死
            timeout = self.config.get('job_timeout', 300)
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(
                    print_engine.print_file,
                    temp_path, job['file_type'], job_id, self._word_lock
                )
                success = fut.result(timeout=timeout)

            if success:
                self.update_status(job_id, 'completed')
                logger.info(f'打印完成: {job["filename"]}')
            else:
                self.update_status(job_id, 'failed', '打印引擎返回失败')
                logger.error(f'打印失败: {job["filename"]}')
        except FuturesTimeout:
            error_msg = f'打印超时 ({timeout}s)'
            self.update_status(job_id, 'failed', error_msg)
            logger.error(f'打印超时: {job["filename"]}')
        except Exception as e:
            error_msg = str(e)
            self.update_status(job_id, 'failed', error_msg)
            logger.error(f'打印异常: {job["filename"]} - {error_msg}')
        finally:
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
        """取消排队中的任务"""
        job = self.get_job(job_id)
        if not job:
            return False, '任务不存在'
        if job['status'] != 'queued':
            return False, '只能取消排队中的任务'
        self.update_status(job_id, 'failed', '用户取消')
        logger.info(f'任务已取消: {job_id}')
        return True, None

    def retry_job(self, job_id):
        """重试失败的任务"""
        job = self.get_job(job_id)
        if not job:
            return None, '任务不存在'
        if job['status'] != 'failed':
            return None, '只能重试失败的任务'
        new_job_id = self.add_job(job['filename'], job['filepath'], job['file_size'], job['file_type'])
        logger.info(f'任务重试: {job_id} -> {new_job_id}')
        return new_job_id, None

    def cleanup_old_jobs(self):
        """清理过期任务 + 恢复卡住的 printing 任务"""
        now = datetime.now()

        # 清理过期历史记录
        cutoff = (now - timedelta(days=self.config.get('job_retention_days', 30))).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM jobs WHERE created_at < ?', (cutoff,))
            conn.commit()
        logger.info('已清理过期任务记录')

        # 心跳检测：找回卡在 printing 超过 5 分钟的任务，重新入队
        heartbeat = (now - timedelta(minutes=5)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            stuck = conn.execute(
                "SELECT id FROM jobs WHERE status='printing' AND created_at < ?",
                (heartbeat,)
            ).fetchall()
            if stuck:
                ids = [row[0] for row in stuck]
                conn.execute(
                    "UPDATE jobs SET status='queued', error_message='心跳恢复' WHERE id IN ({})".format(
                        ','.join('?' * len(ids))
                    ),
                    ids
                )
                conn.commit()
                for jid in ids:
                    self._queue.put(jid)
                logger.warning(f'心跳检测: 已将 {len(ids)} 个卡住的打印任务恢复为排队状态')

    def shutdown(self):
        self._stop_evt.set()
        for w in self._workers:
            w.join(timeout=10)
        self._workers = []
        logger.info('队列管理器已关闭')
