import os
import sqlite3
import threading
import uuid
from typing import Optional
from datetime import datetime, timedelta

from loguru import logger


class JobRepository:
    """任务数据库操作层，封装所有 SQLite 直接访问"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        """初始化数据库连接，db_path 默认为 jobs/jobs.db"""
        if db_path is None:
            from app._paths import persistent_dir, ensure_dir
            db_dir = ensure_dir(persistent_dir(), 'jobs')
            db_path = os.path.join(db_dir, 'jobs.db')
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=False)
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA synchronous=NORMAL')
        self.init_db()

    def _ensure_connection(self) -> None:
        try:
            self._conn.execute('SELECT 1')
        except sqlite3.Error:
            logger.warning('Database connection lost, reconnecting...')
            self._conn.close()
            self._conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
            self._conn.execute('PRAGMA journal_mode=WAL')
            self._conn.execute('PRAGMA synchronous=NORMAL')

    def _execute(self, query, params=None, *, fetchone=False, fetchall=False,
                 row_factory=False, commit=False, executemany=False):
        """统一数据库执行，复用连接 + 线程安全"""
        with self._lock:
            self._ensure_connection()
            if row_factory:
                self._conn.row_factory = sqlite3.Row
            else:
                self._conn.row_factory = None
            try:
                if executemany:
                    cur = self._conn.executemany(query, params or [])
                else:
                    cur = self._conn.execute(query, params or [])
                if commit:
                    self._conn.commit()
                if fetchone:
                    row = cur.fetchone()
                    return dict(row) if row else None
                if fetchall:
                    return [dict(r) for r in cur.fetchall()]
                if executemany:
                    return cur.rowcount
                return cur
            finally:
                self._conn.row_factory = None

    def init_db(self) -> None:
        """建表 + 索引"""
        self._execute('''
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
        ''', commit=True)
        self._execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)', commit=True)
        self._execute('CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)', commit=True)
        self.migrate_db()

    def migrate_db(self) -> None:
        """向后兼容的列添加（已有列跳过）"""
        rows = self._execute("PRAGMA table_info(jobs)", fetchall=True, row_factory=True)
        existing = {row['name'] for row in rows} if rows else set()
        additions = {
            'duplex': 'INTEGER DEFAULT 0',
            'color': 'INTEGER DEFAULT 1',
            'paper_size': "TEXT DEFAULT 'A4'",
            'source': "TEXT DEFAULT 'api'",
            'retry_count': 'INTEGER DEFAULT 0',
        }
        for col, dtype in additions.items():
            if col not in existing:
                self._execute(f'ALTER TABLE jobs ADD COLUMN {col} {dtype}', commit=True)

    def add_job(self, filename: str, filepath: str, file_size: int = 0, file_type: str = '',
                duplex: Optional[int] = None, color: Optional[int] = None,
                copies: Optional[int] = None, paper_size: Optional[str] = None,
                printer_name: Optional[str] = None, source: str = 'api') -> str:
        """插入新任务，返回 job_id"""
        job_id = str(uuid.uuid4())
        self._execute(
            '''INSERT INTO jobs
               (id, filename, filepath, file_size, file_type, status,
                duplex, color, copies, paper_size, printer_name, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (job_id, filename, filepath, file_size, file_type, 'queued',
             duplex, color, copies, paper_size, printer_name, source),
            commit=True
        )
        return job_id

    def get_job(self, job_id: str) -> Optional[dict]:
        """查询单个任务，返回 dict 或 None"""
        return self._execute('SELECT * FROM jobs WHERE id = ?', (job_id,),
                             fetchone=True, row_factory=True)

    def update_status(self, job_id: str, status: str, error_message: Optional[str] = None) -> None:
        """更新任务状态，completed/failed 时同时记录 completed_at"""
        now = datetime.now().isoformat()
        if status in ('completed', 'failed'):
            self._execute(
                'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
                (status, error_message or '', now, job_id), commit=True
            )
        else:
            self._execute('UPDATE jobs SET status = ? WHERE id = ?', (status, job_id), commit=True)

    def _build_where(self, query: str, status: Optional[str], search: Optional[str]) -> tuple[str, list]:
        """构建 WHERE 子句，返回 (query, params)"""
        params = []
        if status:
            query += ' AND status = ?'
            params.append(status)
        if search:
            query += ' AND filename LIKE ?'
            params.append(f'%{search}%')
        return query, params

    def get_jobs(self, status: Optional[str] = None, search: Optional[str] = None,
                 limit: int = 50, offset: int = 0) -> list[dict]:
        """分页查询任务列表，支持按状态和文件名搜索"""
        query, params = self._build_where('SELECT * FROM jobs WHERE 1=1', status, search)
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        return self._execute(query, params, fetchall=True, row_factory=True)

    def count_jobs(self, status: Optional[str] = None, search: Optional[str] = None) -> int:
        """统计任务数量，支持按状态和文件名筛选"""
        query, params = self._build_where('SELECT COUNT(*) AS cnt FROM jobs WHERE 1=1', status, search)
        result = self._execute(query, params, fetchone=True, row_factory=True)
        return result['cnt'] if result else 0

    def get_jobs_by_status(self, status: str) -> list[dict]:
        """按状态查询所有任务"""
        return self._execute('SELECT * FROM jobs WHERE status = ?', (status,),
                             fetchall=True, row_factory=True)

    def get_stats(self) -> dict:
        today = datetime.now().strftime('%Y-%m-%d')
        row = self._execute('''
            SELECT
                COUNT(CASE WHEN status='queued' THEN 1 END) AS queued,
                COUNT(CASE WHEN status='printing' THEN 1 END) AS printing,
                COUNT(CASE WHEN status='completed' THEN 1 END) AS completed_total,
                COUNT(CASE WHEN status='failed' THEN 1 END) AS failed_total,
                COUNT(*) AS total,
                SUM(CASE WHEN status='completed' AND created_at >= ? THEN 1 ELSE 0 END) AS today_completed,
                SUM(CASE WHEN status='failed' AND created_at >= ? THEN 1 ELSE 0 END) AS today_failed
            FROM jobs
        ''', (today, today), fetchone=True, row_factory=True)
        success_total = row['completed_total']
        failed_total = row['failed_total']
        success_rate = (success_total / (success_total + failed_total) * 100) if (success_total + failed_total) > 0 else 100
        return {
            'queued': row['queued'],
            'printing': row['printing'],
            'today_completed': row['today_completed'],
            'today_failed': row['today_failed'],
            'total': row['total'],
            'success_rate': success_rate
        }

    def cleanup_old_jobs(self, retention_days: int = 30) -> int:
        """清理过期历史记录"""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        cur = self._execute('DELETE FROM jobs WHERE created_at < ?', (cutoff,), commit=True)
        deleted = cur.rowcount
        if deleted > 0:
            logger.info(f'已清理 {deleted} 条过期任务记录')
        return deleted

    def increment_retry(self, job_id: str) -> None:
        """递增任务重试计数"""
        self._execute('UPDATE jobs SET retry_count = retry_count + 1 WHERE id = ?',
                      (job_id,), commit=True)

    def batch_update_status(self, job_ids: list[str], status: str, error_message: str = '') -> None:
        """批量更新任务状态（单个事务）"""
        if not job_ids:
            return
        now = datetime.now().isoformat()
        rows = [(status, error_message or '', now, jid) for jid in job_ids]
        self._execute(
            'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
            rows, executemany=True, commit=True
        )

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass
