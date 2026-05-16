import contextlib
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from loguru import logger

from app.printing.migrations import migrate_db
from app.printing.stats import cleanup_old_jobs, get_daily_counts, get_stats


class JobRecord(TypedDict, total=False):
    id: str
    filename: str
    filepath: str
    file_size: int
    file_type: str
    status: str
    error_message: str
    printer_name: str
    copies: int
    duplex: int | None
    color: int | None
    paper_size: str
    source: str
    retry_count: int
    created_at: str
    completed_at: str | None


class JobStats(TypedDict):
    queued: int
    printing: int
    today_completed: int
    today_failed: int
    total: int
    success_rate: float


class JobRepository:
    """任务数据库操作层 — 使用 stdlib sqlite3 同步驱动"""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from app.core._paths import ensure_dir, persistent_dir

            db_dir = ensure_dir(persistent_dir(), 'jobs')
            db_path = db_dir / 'jobs.db'
        self.db_path = str(db_path)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA synchronous=NORMAL')
        self._init_db()

    # ── 执行核心 ──

    def _execute(
        self,
        query: str,
        params: Any = None,
        *,
        fetchone: bool = False,
        fetchall: bool = False,
        commit: bool = False,
        executemany: bool = False,
    ) -> Any:
        with self._lock:
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
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
                if executemany:
                    return cur.rowcount
                return cur
            except sqlite3.OperationalError:
                logger.warning('Database connection lost, reconnecting...')
                with contextlib.suppress(Exception):
                    self._conn.close()
                self._conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                self._conn.execute('PRAGMA journal_mode=WAL')
                self._conn.execute('PRAGMA synchronous=NORMAL')
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
                    rows = cur.fetchall()
                    return [dict(r) for r in rows]
                if executemany:
                    return cur.rowcount
                return cur

    # ── 初始化 + 迁移 ──

    def init_db(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        self._execute(
            """CREATE TABLE IF NOT EXISTS jobs (
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
            )""",
            commit=True,
        )
        self._execute('CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)', commit=True)
        self._execute(
            'CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)', commit=True
        )
        migrate_db(self._execute)

    # ── CRUD ──

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
        job_id = str(uuid.uuid4())
        self._execute(
            """INSERT INTO jobs
               (id, filename, filepath, file_size, file_type, status,
                duplex, color, copies, paper_size, printer_name, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                filename,
                filepath,
                file_size,
                file_type,
                'queued',
                duplex,
                color,
                copies,
                paper_size,
                printer_name,
                source,
            ),
            commit=True,
        )
        return job_id

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._execute('SELECT * FROM jobs WHERE id = ?', (job_id,), fetchone=True)

    def update_status(self, job_id: str, status: str, error_message: str | None = None) -> None:
        now = datetime.now().isoformat()
        if status in ('completed', 'failed'):
            self._execute(
                'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
                (status, error_message or '', now, job_id),
                commit=True,
            )
        else:
            self._execute('UPDATE jobs SET status = ? WHERE id = ?', (status, job_id), commit=True)

    def get_jobs(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        query, params = self._build_where('SELECT * FROM jobs WHERE 1=1', status, search)
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        return self._execute(query, params, fetchall=True)

    def count_jobs(self, status: str | None = None, search: str | None = None) -> int:
        query, params = self._build_where(
            'SELECT COUNT(*) AS cnt FROM jobs WHERE 1=1', status, search
        )
        result = self._execute(query, params, fetchone=True)
        return result['cnt'] if result else 0

    def _build_where(self, query: str, status: str | None, search: str | None) -> tuple[str, list]:
        params = []
        if status:
            query += ' AND status = ?'
            params.append(status)
        if search:
            query += ' AND filename LIKE ?'
            params.append(f'%{search}%')
        return query, params

    def get_jobs_by_status(self, status: str) -> list[JobRecord]:
        return self._execute('SELECT * FROM jobs WHERE status = ?', (status,), fetchall=True)

    def increment_retry(self, job_id: str) -> None:
        self._execute(
            'UPDATE jobs SET retry_count = retry_count + 1 WHERE id = ?', (job_id,), commit=True
        )

    def batch_update_status(self, job_ids: list[str], status: str, error_message: str = '') -> None:
        if not job_ids:
            return
        now = datetime.now().isoformat()
        rows = [(status, error_message or '', now, jid) for jid in job_ids]
        self._execute(
            'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
            rows,
            executemany=True,
            commit=True,
        )

    # ── 统计查询（委托至 stats 模块）──

    def get_stats(self) -> dict:
        return get_stats(self._execute)

    def get_daily_counts(self, days: int = 7) -> dict[str, int]:
        return get_daily_counts(self._execute, days)

    def cleanup_old_jobs(self, retention_days: int = 30) -> int:
        return cleanup_old_jobs(self._execute, retention_days)

    # ── 生命周期 ──

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._conn.close()
