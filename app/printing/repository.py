import asyncio
import contextlib
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

import aiosqlite
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
    """任务数据库操作层 — 使用 aiosqlite 异步驱动

    内部维护专用事件循环线程，对外暴露同步 API，兼容现有 worker/routes 调用者。
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            from app.core._paths import ensure_dir, persistent_dir

            db_dir = ensure_dir(persistent_dir(), 'jobs')
            db_path = db_dir / 'jobs.db'
        self.db_path = str(db_path)

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        try:
            self._conn: aiosqlite.Connection = self._sync(self._connect(), timeout=10)
        except Exception as e:
            logger.error(f'Failed to connect to database: {e}')
            raise
        self._sync(self._init_db(), timeout=10)

    # ── 异步基础设施 ──

    async def _connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.db_path, timeout=5.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute('PRAGMA journal_mode=WAL')
        await conn.execute('PRAGMA synchronous=NORMAL')
        return conn

    def _sync(self, coro, timeout: float = 30):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    async def _ensure_connection(self) -> None:
        try:
            if self._conn is None:
                self._conn = await self._connect()
                return
            await self._conn.execute('SELECT 1')
        except Exception as e:
            logger.warning(f'Database connection lost ({type(e).__name__}), reconnecting...')
            old = self._conn
            self._conn = await self._connect()
            if old is not None:
                with contextlib.suppress(Exception):
                    await old.close()

    async def _execute(
        self,
        query: str,
        params: Any = None,
        *,
        fetchone: bool = False,
        fetchall: bool = False,
        row_factory: bool = False,
        commit: bool = False,
        executemany: bool = False,
    ) -> Any:
        await self._ensure_connection()
        if row_factory:
            self._conn.row_factory = aiosqlite.Row
        else:
            self._conn.row_factory = None
        try:
            if executemany:
                cur = await self._conn.executemany(query, params or [])
            else:
                cur = await self._conn.execute(query, params or [])
            if commit:
                await self._conn.commit()
            if fetchone:
                row = await cur.fetchone()
                return dict(row) if row else None
            if fetchall:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]
            if executemany:
                return cur.rowcount
            return cur
        finally:
            self._conn.row_factory = None

    # ── 初始化 + 迁移 ──

    def init_db(self) -> None:
        self._sync(self._init_db())

    async def _init_db(self) -> None:
        await self._execute(
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
        await self._execute(
            'CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)', commit=True
        )
        await self._execute(
            'CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)', commit=True
        )
        await migrate_db(self._execute)

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
        return self._sync(
            self._add_job(
                filename,
                filepath,
                file_size,
                file_type,
                duplex,
                color,
                copies,
                paper_size,
                printer_name,
                source,
            )
        )

    async def _add_job(
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
        await self._execute(
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
        return self._sync(
            self._execute(
                'SELECT * FROM jobs WHERE id = ?', (job_id,), fetchone=True, row_factory=True
            )
        )

    def update_status(self, job_id: str, status: str, error_message: str | None = None) -> None:
        self._sync(self._update_status(job_id, status, error_message))

    async def _update_status(
        self, job_id: str, status: str, error_message: str | None = None
    ) -> None:
        now = datetime.now().isoformat()
        if status in ('completed', 'failed'):
            await self._execute(
                'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
                (status, error_message or '', now, job_id),
                commit=True,
            )
        else:
            await self._execute(
                'UPDATE jobs SET status = ? WHERE id = ?', (status, job_id), commit=True
            )

    def get_jobs(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        return self._sync(self._get_jobs(status, search, limit, offset))

    async def _get_jobs(
        self, status: str | None, search: str | None, limit: int, offset: int
    ) -> list[dict]:
        query, params = await self._build_where('SELECT * FROM jobs WHERE 1=1', status, search)
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        return await self._execute(query, params, fetchall=True, row_factory=True)

    def count_jobs(self, status: str | None = None, search: str | None = None) -> int:
        return self._sync(self._count_jobs(status, search))

    async def _count_jobs(self, status: str | None, search: str | None) -> int:
        query, params = await self._build_where(
            'SELECT COUNT(*) AS cnt FROM jobs WHERE 1=1', status, search
        )
        result = await self._execute(query, params, fetchone=True, row_factory=True)
        return result['cnt'] if result else 0

    async def _build_where(
        self, query: str, status: str | None, search: str | None
    ) -> tuple[str, list]:
        params = []
        if status:
            query += ' AND status = ?'
            params.append(status)
        if search:
            query += ' AND filename LIKE ?'
            params.append(f'%{search}%')
        return query, params

    def get_jobs_by_status(self, status: str) -> list[JobRecord]:
        return self._sync(
            self._execute(
                'SELECT * FROM jobs WHERE status = ?', (status,), fetchall=True, row_factory=True
            )
        )

    def increment_retry(self, job_id: str) -> None:
        self._sync(
            self._execute(
                'UPDATE jobs SET retry_count = retry_count + 1 WHERE id = ?', (job_id,), commit=True
            )
        )

    def batch_update_status(self, job_ids: list[str], status: str, error_message: str = '') -> None:
        if not job_ids:
            return
        self._sync(self._batch_update_status(job_ids, status, error_message))

    async def _batch_update_status(
        self, job_ids: list[str], status: str, error_message: str = ''
    ) -> None:
        now = datetime.now().isoformat()
        rows = [(status, error_message or '', now, jid) for jid in job_ids]
        await self._execute(
            'UPDATE jobs SET status = ?, error_message = ?, completed_at = ? WHERE id = ?',
            rows,
            executemany=True,
            commit=True,
        )

    # ── 统计查询（委托至 stats 模块）──

    def get_stats(self) -> dict:
        return self._sync(get_stats(self._execute))

    def get_daily_counts(self, days: int = 7) -> dict[str, int]:
        return self._sync(get_daily_counts(self._execute, days))

    def cleanup_old_jobs(self, retention_days: int = 30) -> int:
        return self._sync(cleanup_old_jobs(self._execute, retention_days))

    # ── 生命周期 ──

    def close(self) -> None:
        with contextlib.suppress(Exception):
            fut = asyncio.run_coroutine_threadsafe(self._conn.close(), self._loop)
            fut.result(timeout=5)
        with contextlib.suppress(Exception):
            self._loop.call_soon_threadsafe(self._loop.stop)
        with contextlib.suppress(Exception):
            self._thread.join(timeout=5)
        with contextlib.suppress(Exception):
            self._loop.close()
