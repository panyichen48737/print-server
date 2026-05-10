# 架构优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Systematically refactor the entire codebase — fix bugs, restructure directories, split large files, simplify code, add types, and clean up project config.

**Architecture:** Single-process Windows desktop app (PySide6 GUI + FastAPI backend in same process). The plan follows 7 phases: Bug Fix → Directory Restructure → File Splits → Code Simplification → Types → Polish → CI. Each phase produces a green test suite.

**Tech Stack:** Python 3.10+, FastAPI, PySide6, pywin32, aiosqlite, PIL, httpx, pydantic

---

## File Structure Map

### Files to Create

| File | Responsibility |
|------|---------------|
| `app/core/__init__.py` | Core package init |
| `app/core/config.py` | Configuration (moved from `app/config.py`) |
| `app/core/auth.py` | Authentication (moved from `app/auth.py`) |
| `app/core/exceptions.py` | Exception hierarchy (moved from `app/exceptions.py`) |
| `app/core/schemas.py` | Pydantic models (moved from `app/schemas.py`) |
| `app/core/utils.py` | Utility functions (moved from `app/utils.py`) |
| `app/core/_paths.py` | Path management (moved from `app/_paths.py`) |
| `app/core/version.py` | Version info (moved from `app/version.py`) |
| `app/printing/stats.py` | Statistics queries (split from `repository.py`) |
| `app/printing/migrations.py` | DB schema migrations (split from `repository.py`) |
| `app/routes/system.py` | System management routes (split from `api.py`) |
| `app/routes/__init__.py` | Routes package init, APIRouter aggregation |
| `app/services/notifications/__init__.py` | Notifier abstract + HttpNotifier mixin |
| `app/services/notifications/bark.py` | Bark notifier (moved from `services/bark.py`) |
| `app/services/notifications/dingtalk.py` | DingTalk notifier (moved from `services/dingtalk.py`) |
| `app/services/image_processing.py` | Quark image enhancement (moved from `printing/enhancer.py`) |
| `gui/resources/base.qss` | Base theme QSS (extracted from dark.qss/light.qss) |
| `gui/pages/scan_preview.py` | Image preview from scan.py split |
| `gui/pages/scan_ocr.py` | OCR results from scan.py split |
| `gui/pages/update.py` | Update logic from about.py split |
| `tests/gui/test_main_window.py` | GUI main window tests |
| `tests/gui/test_navigation.py` | Sidebar navigation tests |
| `tests/gui/test_event_bridge.py` | EventBridge signal tests |
| `tests/test_repository_connection.py` | DB reconnection tests |
| `tests/test_job_queue_dedup.py` | Queue dedup tests |
| `tests/test_http_client_lifecycle.py` | HTTP client lifecycle tests |

### Files to Modify (non-move)

| File | Change |
|------|--------|
| `app/printing/repository.py` | Remove stats/migrations methods, add `_ensure_connection` in `_execute` |
| `app/printing/worker.py` | Extract RetryHandler, fix race condition (#4) |
| `app/printing/worker_pool.py` | Rename drain() → wait_stop() (#9) |
| `app/printing/job_queue.py` | Add `_queued_ids` set for dedup (#3) |
| `app/printing/engine.py` | Minor import path updates |
| `app/printing/backends/base.py` | Add `cancel_all_spooler_jobs` from printing/utils.py, add `clear_backend_registry()` |
| `app/printing/backends/image.py` | Minor import path updates |
| `app/routes/api.py` | Remove system routes, keep printing routes |
| `app/routes/ws.py` | No change |
| `app/services/sse_broadcaster.py` | Merge LogBroadcaster, fix lock granularity (#8) |
| `app/services/upload.py` | Import path update |
| `app/services/printer_monitor.py` | No change |
| `app/services/heartbeat.py` | No change |
| `app/bootstrap.py` | Update import paths, add shutdown handler (#5), HTTP client lifecycle (#2) |
| `app/__init__.py` | Import path updates |
| `app/logging.py` | No change |
| `gui/app.py` | Import path updates, PageBase usage |
| `gui/pages/scan.py` | Delegate to scan_preview.py + scan_ocr.py, slim down |
| `gui/pages/about.py` | Delegate update logic to update.py, slim down |
| `gui/event_bridge.py` | Type annotations |
| `pyproject.toml` | Remove textual/typer, update mypy files, add gui/ |
| `.github/workflows/ci.yml` | Fix `mypy app/ console/` → `app/ launcher/`, fix launcher/ exclude |

### Files to Delete

| File | Reason |
|------|--------|
| `app/printing/utils.py` | Merged into backends/base.py |
| `app/printing/enhancer.py` | Moved to services/image_processing.py |
| `app/services/notifier.py` | Replaced by notifications/__init__.py |
| `app/services/log_broadcaster.py` | Merged into sse_broadcaster.py |
| `app/services/bark.py` | Moved to notifications/bark.py |
| `app/services/dingtalk.py` | Moved to notifications/dingtalk.py |
| `app/config.py` | Moved to core/config.py |
| `app/auth.py` | Moved to core/auth.py |
| `app/exceptions.py` | Moved to core/exceptions.py |
| `app/schemas.py` | Moved to core/schemas.py |
| `app/utils.py` | Moved to core/utils.py |
| `app/_paths.py` | Moved to core/_paths.py |
| `app/version.py` | Moved to core/version.py |

---

## Phase 1: Bug Fixes

### Task 1.1: Fix `_ensure_connection` dead code (#1)

**Files:**
- Modify: `app/printing/repository.py:47-55`

- [ ] **Step 1: Update `_execute` to call health check before query**

Replace the `_execute` method:

```python
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
    self._ensure_connection()  # ← ADD THIS LINE
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
```

- [ ] **Step 2: Run tests to verify**

Run: `pytest tests/ -v --tb=short`
Expected: All 99+ tests pass

- [ ] **Step 3: Commit**

```bash
git add app/printing/repository.py
git commit -m "fix: add _ensure_connection call to _execute in repository"
```

### Task 1.2: Fix module-level HTTP client leak (#2)

**Files:**
- Modify: `app/services/bark.py:9`
- Modify: `app/services/dingtalk.py:9`
- Modify: `app/bootstrap.py`

- [ ] **Step 1: Remove module-level `_client` from bark.py**

```python
# Before (line 8-9):
import httpx
_client = httpx.Client(timeout=10)

# After: remove _client, accept client in constructor
```

- [ ] **Step 2: Remove module-level `_client` from dingtalk.py**

Same pattern as bark.py.

- [ ] **Step 3: Update bootstrap to create and inject HTTP client**

In `bootstrap.py`, update the `_server_lifespan` (or bootstrap function) to create an httpx.Client and pass it to notifiers.

- [ ] **Step 4: Run tests to verify**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/services/bark.py app/services/dingtalk.py app/bootstrap.py
git commit -m "fix: inject httpx.Client instead of module-level leak"
```

### Task 1.3: Fix `recover_stuck_jobs` duplicate submit (#3)

**Files:**
- Modify: `app/printing/job_queue.py:144-152`

- [ ] **Step 1: Add `_queued_ids` tracking set to JobQueue**

```python
# In __init__:
class JobQueue:
    def __init__(self, repo: JobRepository, event_bus: Any = None) -> None:
        self._repo = repo
        self._event_bus = event_bus
        self._queue: queue.Queue = queue.Queue()
        self._cancelled_ids: set[str] = set()
        self._cancelled_lock = threading.Lock()
        self._queued_ids: set[str] = set()  # ← ADD
        self._queued_ids_lock = threading.Lock()  # ← ADD
```

- [ ] **Step 2: Track job_id on add and remove on get**

In `add_job()`, add to `_queued_ids` after queue.put.
In `get_for_processing()`, remove from `_queued_ids` after queue.get.

```python
def add_job(self, ...):
    job_id = self._repo.add_job(...)
    self._queue.put(job_id)
    with self._queued_ids_lock:
        self._queued_ids.add(job_id)  # ← ADD
    logger.info(f'任务已入队: {job_id} - {filename}')
    return job_id

def get_for_processing(self, timeout: float = 1.0) -> str | None:
    try:
        job_id = self._queue.get(timeout=timeout)
        with self._queued_ids_lock:
            self._queued_ids.discard(job_id)  # ← ADD
        return job_id
    except queue.Empty:
        return None
```

- [ ] **Step 3: Guard `recover_stuck_jobs` against duplicate**

```python
def recover_stuck_jobs(self) -> None:
    heartbeat = (datetime.now() - timedelta(minutes=5)).isoformat()
    stuck_jobs = self._repo.get_jobs_by_status('printing')
    stuck_ids = [j['id'] for j in stuck_jobs if j['created_at'] < heartbeat]
    with self._queued_ids_lock:
        already_queued = self._queued_ids.copy()
    for jid in stuck_ids:
        if jid in already_queued:
            continue  # ← SKIP if already in queue
        self._repo.update_status(jid, 'queued', '心跳恢复')
        self._queue.put(jid)
        with self._queued_ids_lock:
            self._queued_ids.add(jid)
    if stuck_ids:
        logger.warning(f'心跳检测: 已将 {len(stuck_ids)} 个卡住的打印任务恢复为排队状态')
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/printing/job_queue.py
git commit -m "fix: prevent recover_stuck_jobs from duplicate job submission"
```

### Task 1.4: Fix cancel race condition (#4)

**Files:**
- Modify: `app/printing/worker.py:46-58`

- [ ] **Step 1: Move cancel check into the try block, re-check after status update**

```python
def execute(self, job_id: str, worker_id: int, attempt: int = 0) -> tuple[bool, str | None]:
    job = self._repo.get_job(job_id)
    if not job:
        return True, None

    filename = job['filename']
    prefix = f'[{worker_id}]'
    if attempt == 0:
        logger.info(f'{prefix} 开始打印: {filename}')
    else:
        logger.info(f'{prefix} 第 {attempt} 次重试: {filename}')

    # Check cancel BEFORE updating status
    if self._is_cancelled(job_id):
        return True, None

    self._update_and_broadcast(
        job_id, 'printing', filename=filename, source=job.get('source', 'api')
    )

    # Re-check cancel AFTER status update (closes the race window)
    if self._is_cancelled(job_id):
        self._repo.update_status(job_id, 'failed', '用户取消')
        self._update_and_broadcast(job_id, 'failed', '用户取消', filename, job.get('source', 'api'))
        return True, None

    original_path = job['filepath']
    temp_path = None
    try:
        ...  # rest of execute unchanged
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add app/printing/worker.py
git commit -m "fix: close cancel race window between status check and broadcast"
```

### Task 1.5: Fix `start_watcher()` without shutdown (#5)

**Files:**
- Modify: `app/bootstrap.py`
- Modify: `app/__init__.py`

- [ ] **Step 1: Ensure `ServerHandle` or bootstrap calls `config.stop_watcher()` on shutdown**

In `bootstrap.py` or the `_server_lifespan`, add stop_watcher call:

```python
@asynccontextmanager
async def _server_lifespan(_app):
    logger.info('服务器启动完成')
    yield
    logger.info('服务器关闭中...')
    ref = _lifespan_ref
    if ref.config:
        ref.config.stop_watcher()       # Ensure watcher is stopped
    if ref.printer_monitor:
        ref.printer_monitor.stop()
    if ref.heartbeat:
        ref.heartbeat.stop()
    if ref.worker_pool:
        ref.worker_pool.stop()
    logger.info('服务器已完全关闭')
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add app/bootstrap.py
git commit -m "fix: ensure config.stop_watcher() is called on server shutdown"
```

### Task 1.6: Fix `__del__` in QuarkEnhancer (#6)

**Files:**
- Modify: `app/printing/enhancer.py:21-27`

- [ ] **Step 1: Remove `__del__`, add `close()` method**

```python
class QuarkEnhancer:
    def __init__(self, config: Any) -> None:
        self.config = config
        self._client = httpx.Client(timeout=60)

    def close(self) -> None:
        """Explicit cleanup — call when done."""
        with contextlib.suppress(Exception):
            self._client.close()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add app/printing/enhancer.py
git commit -m "fix: replace __del__ with explicit close() in QuarkEnhancer"
```

---

## Phase 2: Directory Structure

### Task 2.1: Create `app/core/` package and move files

**Files:**
- Create: `app/core/__init__.py`
- Move: `app/config.py` → `app/core/config.py`
- Move: `app/auth.py` → `app/core/auth.py`
- Move: `app/exceptions.py` → `app/core/exceptions.py`
- Move: `app/schemas.py` → `app/core/schemas.py`
- Move: `app/utils.py` → `app/core/utils.py`
- Move: `app/_paths.py` → `app/core/_paths.py`
- Move: `app/version.py` → `app/core/version.py`

- [ ] **Step 1: Create `app/core/__init__.py`** (empty file)

- [ ] **Step 2: Copy each source file to `app/core/` with updated internal imports**

For each file, update relative imports that reference `app.config` etc. to `app.core.config`:

```python
# Example: In app/core/config.py, update from app._paths import ... to from app.core._paths import ...
from app.core._paths import config_dir
```

- [ ] **Step 3: Verify the moved files work**

Run: `python -c "from app.core.config import Config; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Update all imports across the codebase**

Files that import from `app.config`, `app.auth`, `app.exceptions`, `app.schemas`, `app.utils`, `app._paths`, `app.version` → change to `app.core.*`

- [x] **Step 5: Do NOT delete originals yet** (will do after all import paths verified)

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 7: Delete originals and run tests again**

```bash
git rm app/config.py app/auth.py app/exceptions.py app/schemas.py app/utils.py app/_paths.py app/version.py
pytest tests/ -v --tb=short
```
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add app/core/ && git add -u && git rm app/config.py app/auth.py app/exceptions.py app/schemas.py app/utils.py app/_paths.py app/version.py
git commit -m "refactor: move core modules to app/core/ package"
```

### Task 2.2: Create `app/services/notifications/` package and move files

**Files:**
- Create: `app/services/notifications/__init__.py`
- Move: `app/services/bark.py` → `app/services/notifications/bark.py`
- Move: `app/services/dingtalk.py` → `app/services/notifications/dingtalk.py`

- [ ] **Step 1: Create `app/services/notifications/__init__.py`**

```python
"""通知服务包 — Notifier 抽象 + HTTP 通知基类"""

import abc
from typing import Any

import httpx


class Notifier(abc.ABC):
    @abc.abstractmethod
    def send_notification(self, title: str, message: str, level: str = 'info') -> None: ...

    @abc.abstractmethod
    def notify_job_completed(self, filename: str, time_str: str) -> None: ...

    @abc.abstractmethod
    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None: ...


class HttpNotifier:
    """HTTP 通知基类混入 — 管理 httpx.Client 生命周期"""

    def __init__(self, client: httpx.Client | None = None):
        self._http = client or httpx.Client(timeout=10)

    def _post(self, url: str, json: dict, timeout: float = 10) -> bool:
        try:
            resp = self._http.post(url, json=json, timeout=timeout)
            if resp.status_code == 200:
                return True
        except Exception:
            pass
        return False
```

- [ ] **Step 2: Move bark.py and dingtalk.py, update imports to use notifications package**

```python
# notifications/bark.py
from app.services.notifications import Notifier, HttpNotifier, format_error_message

class BarkNotifier(Notifier, HttpNotifier):
    def __init__(self, config: Any, client: httpx.Client | None = None) -> None:
        self.config = config
        HttpNotifier.__init__(self, client)

    def send_notification(self, title: str, message: str, _level: str = 'info') -> None:
        if self.config.get('notify_channel', 'disabled') != 'bark':
            return
        key = self.config.get('bark_key', '')
        if not key:
            return
        server = self.config.get('bark_server', 'https://api.day.app')
        payload = {'title': title, 'body': message, 'group': 'PrintServer'}
        if self._post(f'{server}/{key}', payload):
            logger.info('Bark 通知发送成功')
        else:
            logger.warning('Bark 通知发送失败')
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add app/services/notifications/ && git rm app/services/bark.py app/services/dingtalk.py && git add -u
git commit -m "refactor: move notifiers to app/services/notifications/ package"
```

### Task 2.3: Move enhancer and merge utils

**Files:**
- Move: `app/printing/enhancer.py` → `app/services/image_processing.py`
- Merge: `app/printing/utils.py` → into `app/printing/backends/base.py`

- [ ] **Step 1: Copy enhancer.py to services/image_processing.py, update import path**

- [ ] **Step 2: Add cancel_all_spooler_jobs to backends/base.py**

```python
# At end of app/printing/backends/base.py

def cancel_all_spooler_jobs(printer_name: str) -> None:
    """取消指定打印机的所有 Spooler 作业"""
    import win32print
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(handle, 0, 0xFFFFFFFF, 1)
            for job in jobs:
                win32print.SetJob(handle, job['JobId'], 0, win32print.JOB_CONTROL_DELETE)
        finally:
            win32print.ClosePrinter(handle)
    except Exception as e:
        logger.warning(f'取消 Spooler 作业失败: {e}')
```

- [ ] **Step 3: Update pdf.py import**

```python
# In app/printing/backends/pdf.py
# Change: from app.printing.utils import cancel_all_spooler_jobs
# To:     from app.printing.backends.base import cancel_all_spooler_jobs
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git mv app/printing/enhancer.py app/services/image_processing.py && git rm app/printing/utils.py && git add -u
git commit -m "refactor: move enhancer to services/, merge printing/utils into backends/base"
```

### Task 2.4: Merge LogBroadcaster into SSEBroadcaster

**Files:**
- Merge: `app/services/log_broadcaster.py` → into `app/services/sse_broadcaster.py`

- [ ] **Step 1: Add LogBroadcaster class into sse_broadcaster.py**

```python
# At end of app/services/sse_broadcaster.py


class LogBroadcaster:
    """loguru sink — 将日志推送到 SSE"""

    def __init__(self, broadcaster: SSEBroadcaster | None = None):
        self._broadcaster = broadcaster

    def write(self, message: str) -> None:
        if message.strip() and self._broadcaster:
            self._broadcaster.publish(
                'log',
                {
                    'message': message.strip(),
                    'level': 'INFO',
                    'name': 'print_server',
                },
            )


# Keep LogBroadcaster export for backwards compat
__all__ = ['EventBus', 'SSEBroadcaster', 'LogBroadcaster', 'init_app']
```

- [ ] **Step 2: Update bootstrap.py import**

```python
# Change: from app.services.log_broadcaster import LogBroadcaster
# To:     from app.services.sse_broadcaster import LogBroadcaster
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Remove old log_broadcaster.py**

```bash
git rm app/services/log_broadcaster.py
pytest tests/ -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git rm app/services/log_broadcaster.py && git add -u
git commit -m "refactor: merge LogBroadcaster into sse_broadcaster.py"
```

---

## Phase 3: Large File Splits

### Task 3.1: Split repository.py (326 → 3 files)

**Files:**
- Modify: `app/printing/repository.py` — keep CRUD only, ~120 lines
- Create: `app/printing/stats.py` — statistics queries
- Create: `app/printing/migrations.py` — schema migrations

- [ ] **Step 1: Create `app/printing/migrations.py`**

```python
"""数据库 schema 迁移"""

from typing import Any

from loguru import logger


async def init_db(execute_fn) -> None:
    """初始化数据库表"""
    await execute_fn(
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
    await execute_fn(
        'CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)', commit=True
    )
    await execute_fn(
        'CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)', commit=True
    )


async def migrate_db(execute_fn, conn: Any) -> None:
    """运行增量迁移"""
    import aiosqlite

    conn.row_factory = aiosqlite.Row
    cursor = await execute_fn('PRAGMA table_info(jobs)', fetchall=True, row_factory=True)
    existing = {row['name'] for row in cursor} if cursor else set()
    additions = {
        'duplex': 'INTEGER DEFAULT 0',
        'color': 'INTEGER DEFAULT 1',
        'paper_size': "TEXT DEFAULT 'A4'",
        'source': "TEXT DEFAULT 'api'",
        'retry_count': 'INTEGER DEFAULT 0',
    }
    for col, dtype in additions.items():
        if col not in existing:
            await execute_fn(f'ALTER TABLE jobs ADD COLUMN {col} {dtype}', commit=True)
```

- [ ] **Step 2: Create `app/printing/stats.py`**

```python
"""统计查询"""

from datetime import datetime
from typing import Any


async def get_stats(execute_fn) -> dict:
    """获取任务统计信息"""
    today = datetime.now().strftime('%Y-%m-%d')
    row = await execute_fn(
        """SELECT
            COUNT(CASE WHEN status='queued' THEN 1 END) AS queued,
            COUNT(CASE WHEN status='printing' THEN 1 END) AS printing,
            COUNT(CASE WHEN status='completed' THEN 1 END) AS completed_total,
            COUNT(CASE WHEN status='failed' THEN 1 END) AS failed_total,
            COUNT(*) AS total,
            SUM(CASE WHEN status='completed' AND created_at >= ? THEN 1 ELSE 0 END) AS today_completed,
            SUM(CASE WHEN status='failed' AND created_at >= ? THEN 1 ELSE 0 END) AS today_failed
        FROM jobs""",
        (today, today),
        fetchone=True,
        row_factory=True,
    )
    success_total = row['completed_total'] or 0
    failed_total = row['failed_total'] or 0
    total = success_total + failed_total
    success_rate = (success_total / total * 100) if total > 0 else 100
    return {
        'queued': row['queued'] or 0,
        'printing': row['printing'] or 0,
        'today_completed': row['today_completed'] or 0,
        'today_failed': row['today_failed'] or 0,
        'total': row['total'] or 0,
        'success_rate': success_rate,
    }


async def get_daily_counts(execute_fn, days: int = 7) -> dict[str, int]:
    """获取每日任务统计"""
    cursor = await execute_fn(
        "SELECT DATE(created_at) as day, COUNT(*) as cnt FROM jobs "
        "WHERE created_at >= datetime('now', ? || ' days') "
        "GROUP BY day ORDER BY day",
        (-days,),
        fetchall=True,
        row_factory=True,
    )
    return {row['day']: row['cnt'] for row in cursor} if cursor else {}
```

- [ ] **Step 3: Slim down `repository.py`** — remove stats/migrations methods, keep CRUD

- [ ] **Step 4: Update `repository.py.__init__` to call migrations from new module**

```python
# In _init_db, change:
#   await self._migrate_db()
# To:
#   from app.printing.migrations import migrate_db
#   await migrate_db(self._execute, self._conn)
```

- [ ] **Step 5: Update all callers** — `get_stats()` → call from stats module

- [ ] **Step 6: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add app/printing/stats.py app/printing/migrations.py && git add -u
git commit -m "refactor: split repository.py into crud/stats/migrations"
```

### Task 3.2: Split api.py (301 → 2 files)

**Files:**
- Modify: `app/routes/api.py` — keep only print-related routes
- Create: `app/routes/system.py` — system management routes
- Create: `app/routes/__init__.py` — APIRouter aggregation

- [ ] **Step 1: Create `app/routes/system.py`**

Move these endpoints from api.py:
- /health
- /version
- /logs
- /printers
- /printers/status
- /stats
- /jobs
- /test_notification
- /set_default_printer
- /events (SSE)

```python
"""系统管理路由 — 监控、统计、配置"""

import time
from collections import deque
from pathlib import Path

import msgspec
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.core._paths import persistent_dir
from app.core.schemas import (
    HealthResponse, LogsResponse, NotificationTestResponse,
    PrinterListResponse, PrinterStatusResponse, SetDefaultPrinterRequest,
)
from app.core.utils import format_time
from app.core.version import __build_date__, __pyinstaller_version__, __version__

system_router = APIRouter()
_start_time = time.time()


@system_router.get('/health', response_model=HealthResponse)
async def health(request: Request):
    db_path = Path(persistent_dir()) / 'jobs.db'
    db_size = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
    return {
        'status': 'ok', 'version': __version__,
        'uptime': int(time.time() - _start_time),
        'queue_size': request.app.state.job_queue.queue_size(),
        'db_size_mb': round(db_size, 1),
        'port': getattr(request.app.state, 'port', 5000),
    }


@system_router.get('/version')
async def api_version():
    return {
        'version': __version__,
        'python_version': __import__('sys').version.split()[0],
        'build_date': __build_date__,
        'pyinstaller': __pyinstaller_version__,
    }


@system_router.get('/logs', response_model=LogsResponse)
async def api_logs(request: Request, lines: int = 50):
    log_file = Path(persistent_dir()) / 'logs' / 'print_server.log'
    try:
        with open(log_file, encoding='utf-8', errors='replace') as f:
            last_lines = deque(f, maxlen=lines)
        return {'lines': list(last_lines)}
    except FileNotFoundError:
        return {'lines': []}
    except Exception as e:
        return {'lines': [f'[ERROR] 读取日志失败: {e}']}


@system_router.get('/printers', response_model=PrinterListResponse)
async def list_printers(request: Request):
    monitor = request.app.state.printer_monitor
    return {'printers': list(monitor.get_all_statuses().keys())}


@system_router.get('/printers/status', response_model=PrinterStatusResponse)
async def printer_status(request: Request):
    monitor = request.app.state.printer_monitor
    return {'printers': monitor.get_all_statuses()}


@system_router.get('/stats')
async def api_stats_json(request: Request):
    repo = request.app.state.job_repo
    from app.printing.stats import get_stats as _get_stats, get_daily_counts
    stats = repo._sync(_get_stats(repo._execute))
    stats['daily_counts'] = repo._sync(get_daily_counts(repo._execute, 7))
    return stats


@system_router.get('/jobs')
async def api_jobs(
    request: Request, limit: int = 20, offset: int = 0,
    status: str | None = None, search: str | None = None,
):
    repo = request.app.state.job_repo
    jobs = repo.get_jobs(status=status or None, search=search or None, limit=limit, offset=offset)
    total = repo.count_jobs(status=status or None, search=search or None)
    return {'jobs': jobs, 'total': total}


@system_router.post('/set_default_printer')
async def set_default_printer(request: Request, body: SetDefaultPrinterRequest):
    config = request.app.state.app_config
    config.set('default_printer', body.printer)
    config.save()
    logger.info(f'默认打印机已设置: {body.printer}')
    return {'success': True}


@system_router.post('/test_notification', response_model=NotificationTestResponse)
async def test_notification(request: Request, background_tasks: BackgroundTasks):
    config = request.app.state.app_config
    channel = config.get('notify_channel', 'disabled')
    time_str = format_time()

    def _send():
        dingtalk = getattr(request.app.state, 'dingtalk', None)
        bark = getattr(request.app.state, 'bark', None)
        try:
            if channel == 'dingtalk' and dingtalk:
                dingtalk.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}', level='info')
            elif channel == 'bark' and bark:
                bark.send_notification('测试通知', f'这是一条测试消息\n时间: {time_str}')
        except Exception as e:
            logger.warning(f'发送测试通知失败: {e}')

    background_tasks.add_task(_send)
    return {'success': True, 'channel': channel}


@system_router.get('/events')
async def sse_events(request: Request):
    """Server-Sent Events endpoint"""
    broadcaster = request.app.state.sse
    sub_id, q = broadcaster.subscribe()
    import queue as _queue
    import time as _time
    start = _time.monotonic()
    max_duration = 3600

    def generate():
        _encoder = msgspec.json.Encoder()
        try:
            while True:
                elapsed = _time.monotonic() - start
                if elapsed > max_duration:
                    break
                try:
                    event_type, data = q.get(timeout=30)
                    yield f'event: {event_type}\ndata: {_encoder.encode(data).decode("utf-8")}\n\n'
                except _queue.Empty:
                    continue
        except GeneratorExit:
            pass
        finally:
            broadcaster.unsubscribe(sub_id)

    return StreamingResponse(generate(), media_type='text/event-stream')
```

- [ ] **Step 2: Create `app/routes/__init__.py`**

```python
"""路由聚合"""

from app.routes.api import api_router
from app.routes.system import system_router

__all__ = ['api_router', 'system_router']
```

- [ ] **Step 3: Update `app/__init__.py` to register both routers**

```python
# Replace: app.include_router(api_router, prefix='/api')
# With:
from app.routes.api import api_router
from app.routes.system import system_router
app.include_router(api_router, prefix='/api')
app.include_router(system_router, prefix='/api')
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/routes/system.py app/routes/__init__.py && git add -u
git commit -m "refactor: split api.py into api.py and system.py"
```

### Task 3.3: Restructure worker.py internally

**Files:**
- Modify: `app/printing/worker.py`

- [ ] **Step 1: Extract RetryHandler class**

Add this before JobWorker:

```python
class RetryHandler:
    """重试策略封装"""

    def __init__(self, config, repo):
        self._config = config
        self._repo = repo

    def max_retries(self) -> int:
        return self._config.get('auto_retry_count', 0)

    def should_retry(self, attempt: int, error_msg: str) -> bool:
        if attempt >= self.max_retries():
            return False
        if error_msg == '用户取消':
            return False
        return True

    def prepare_retry(self, job_id: str, attempt: int, max_retries: int) -> None:
        self._repo.update_status(job_id, 'queued', f'重试 {attempt + 1}/{max_retries}')
        self._repo.increment_retry(job_id)
```

- [ ] **Step 2: Update `JobWorker._process` to use RetryHandler**

```python
def _process(self, job_id):
    retry = RetryHandler(self._config, self._repo)
    max_retries = retry.max_retries()
    job = self._repo.get_job(job_id)
    if not job or self._job_queue.is_cancelled(job_id):
        return
    for attempt in range(max_retries + 1):
        success, error_msg = self._executor.execute(job_id, self.worker_id, attempt)
        if success:
            return
        if retry.should_retry(attempt, error_msg):
            retry.prepare_retry(job_id, attempt, max_retries)
            continue
        break
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add app/printing/worker.py
git commit -m "refactor: extract RetryHandler in worker.py"
```

### Task 3.4: Split scan.py (667 → 3 files)

**Files:**
- Modify: `gui/pages/scan.py` — slim down to ~350 lines
- Create: `gui/pages/scan_preview.py` — image preview + crop/rotate
- Create: `gui/pages/scan_ocr.py` — OCR results display

- [ ] **Step 1: Create `gui/pages/scan_preview.py`**

```python
"""Scanner image preview widget — crop, rotate, zoom"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QVBoxLayout, QWidget, QHBoxLayout, QPushButton


class ScanPreview(QWidget):
    """Image preview with zoom and rotation controls"""
    rotate_left_clicked = Signal()
    rotate_right_clicked = Signal()
    crop_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.view = QGraphicsView()
        self.scene = QGraphicsScene()
        self.view.setScene(self.scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        layout.addWidget(self.view)

        toolbar = QHBoxLayout()
        btn_rotate_l = QPushButton("↺ 左旋")
        btn_rotate_r = QPushButton("↻ 右旋")
        toolbar.addWidget(btn_rotate_l)
        toolbar.addWidget(btn_rotate_r)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        btn_rotate_l.clicked.connect(self.rotate_left_clicked.emit)
        btn_rotate_r.clicked.connect(self.rotate_right_clicked.emit)

    def set_image(self, image: QImage):
        self.scene.clear()
        pixmap = QPixmap.fromImage(image)
        self._pixmap_item = self.scene.addPixmap(pixmap)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def clear(self):
        self.scene.clear()
        self._pixmap_item = None
```

- [ ] **Step 2: Create `gui/pages/scan_ocr.py`**

```python
"""OCR result display widget"""

from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget, QLabel


class ScanOcrResult(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("OCR 识别结果"))
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

    def set_text(self, text: str):
        self.text_edit.setPlainText(text)

    def clear(self):
        self.text_edit.clear()
```

- [ ] **Step 3: Slim down `scan.py`** — import and delegate to ScanPreview + ScanOcrResult

- [ ] **Step 4: Run GUI smoke test**

Run: `python -c "from gui.pages.scan_preview import ScanPreview; from gui.pages.scan_ocr import ScanOcrResult; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add gui/pages/scan_preview.py gui/pages/scan_ocr.py && git add -u
git commit -m "refactor: split scan.py into scan + scan_preview + scan_ocr"
```

### Task 3.5: Split about.py (514 → 2 files)

**Files:**
- Modify: `gui/pages/about.py` — keep about info only
- Create: `gui/pages/update.py` — update check/download/install logic

- [ ] **Step 1: Create `gui/pages/update.py`**

```python
"""Update checker widget — check, download, and install updates"""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar
from loguru import logger


class UpdateWidget(QWidget):
    """Update management widget with check, download, install"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.status_label = QLabel("正在检查更新...")
        layout.addWidget(self.status_label)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.check_btn = QPushButton("检查更新")
        self.check_btn.clicked.connect(self.check)
        layout.addWidget(self.check_btn)

    def check(self):
        """Check for updates in background thread"""
        from app.updater import check_latest_version
        self.status_label.setText("正在检查更新...")

        def _worker():
            info = check_latest_version()
            QTimer.singleShot(0, lambda: self._on_result(info))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_result(self, info):
        if info and info.is_newer:
            self.status_label.setText(f"新版本可用: {info.version}")
            self.progress.setVisible(True)
        else:
            self.status_label.setText("已是最新版本")
```

- [ ] **Step 2: Slim down `about.py`** — keep only About info UI, delegate update to UpdateWidget

- [ ] **Step 3: Run GUI smoke test**

Run: `python -c "from gui.pages.update import UpdateWidget; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add gui/pages/update.py && git add -u
git commit -m "refactor: split about.py into about + update"
```

---

## Phase 4: Code Simplification

### Task 4.1: Add `temp_print_file` context manager

**Files:**
- Modify: `app/core/utils.py` — add contextmanager

- [ ] **Step 1: Add to `app/core/utils.py`**

```python
import contextlib
import os
import tempfile
from pathlib import Path


@contextlib.contextmanager
def temp_print_file(suffix: str = ''):
    """自动清理的临时打印文件"""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    try:
        yield tmp.name
    finally:
        safe_remove(tmp.name)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add app/core/utils.py
git commit -m "refactor: add temp_print_file context manager to core/utils"
```

### Task 4.2: Replace error string matching with exception types

**Files:**
- Modify: `app/core/exceptions.py` — add error codes
- Modify: `app/bootstrap.py` — update notification callback

- [ ] **Step 1: Update exceptions.py with error context**

```python
class PrintServerError(Exception):
    """所有打印服务器异常的基类"""
    def __init__(self, message: str, *, job_id: str | None = None, filename: str | None = None):
        self.job_id = job_id
        self.filename = filename
        super().__init__(message)


class ConfigError(PrintServerError, ValueError): ...
class AuthError(PrintServerError): ...
class PrintError(PrintServerError, RuntimeError): ...
class FileTypeError(PrintServerError, ValueError): ...
class JobCanceled(PrintServerError): ...
class TimeoutError(PrintServerError): ...
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add app/core/exceptions.py
git commit -m "refactor: enhance exception hierarchy with error context fields"
```

### Task 4.3: Simplify notifier.py → notifications/__init__.py

**Files:**
- Create: `app/services/notifications/__init__.py` (replace old notifier.py)
- Delete: `app/services/notifier.py`

- [ ] **Step 1: Write updated notifications/__init__.py** (copy from Task 2.2, add format_error_message)

- [ ] **Step 2: Update bootstrap.py import**

```python
# Change: from app.services.notifier import is_print_related_error
# To:     from app.services.notifications import is_system_error
```

- [ ] **Step 3: Delete old notifier.py**

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git rm app/services/notifier.py && git add app/services/notifications/__init__.py && git add -u
git commit -m "refactor: replace notifier.py with notifications/__init__.py"
```

### Task 4.4: QSS theme dedup

**Files:**
- Create: `gui/resources/base.qss`
- Modify: `gui/resources/dark.qss`
- Modify: `gui/resources/light.qss`

- [ ] **Step 1: Extract common QSS to base.qss**

Create base.qss with all structural rules (widget types, layout, etc.) — everything except color values.

- [ ] **Step 2: Slim down dark.qss and light.qss** — keep only color definitions, import base.qss

- [ ] **Step 3: Run GUI smoke test**

Run: `python -c "from gui.app import MainWindow; print('QSS loaded')"`
Expected: No errors (QSS paths resolve)

- [ ] **Step 4: Commit**

```bash
git add gui/resources/base.qss && git add -u
git commit -m "refactor: deduplicate QSS themes with shared base.qss"
```

---

## Phase 5: Type Annotations

### Task 5.1: Add types to repository.py

**Files:**
- Modify: `app/printing/repository.py`

- [ ] **Step 1: Add TypedDict for job records**

```python
from typing import Any, TypedDict

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
    created_at: str
    completed_at: str
    duplex: int
    color: int
    paper_size: str
    source: str
    retry_count: int
```

- [ ] **Step 2: Add return type annotations**

```python
def get_job(self, job_id: str) -> JobRecord | None: ...
def get_jobs(self, ...) -> list[JobRecord]: ...
def get_jobs_by_status(self, status: str) -> list[JobRecord]: ...
```

- [ ] **Step 3: Run mypy to verify**

Run: `mypy app/printing/repository.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add app/printing/repository.py
git commit -m "types: add TypedDict and return type annotations to repository"
```

### Task 5.2: Add types to worker.py and engine.py

**Files:**
- Modify: `app/printing/worker.py`
- Modify: `app/printing/engine.py`

- [ ] **Step 1: Annotate worker.py**

```python
class JobExecutor:
    def __init__(
        self,
        config: Any,
        event_bus: Any,
        repo: 'JobRepository',
        print_engine: Any,
        get_cancelled_fn: Callable[[str], bool],
        word_lock: threading.Lock,
    ) -> None: ...

    def execute(self, job_id: str, worker_id: int, attempt: int = 0) -> tuple[bool, str | None]: ...
```

- [ ] **Step 2: Annotate engine.py**

```python
class PrintEngine:
    def print_file(
        self,
        filepath: str,
        file_type: str,
        job_id: str,
        word_lock: threading.Lock | None,
        print_params: dict[str, Any] | None = None,
    ) -> bool: ...
```

- [ ] **Step 3: Run mypy to verify**

Run: `mypy app/printing/`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add app/printing/worker.py app/printing/engine.py
git commit -m "types: add type annotations to worker and engine"
```

### Task 5.3: Clean up unused dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Remove `textual` and `typer` from dependencies**

In pyproject.toml, remove:
```
"textual>=1.0.0",
"typer>=0.15.0",
```

- [ ] **Step 2: Update mypy config to include gui/**

```toml
[tool.mypy]
python_version = "3.10"
warn_unused_ignores = true
strict_optional = true
ignore_missing_imports = true
files = ["app/", "gui/", "launcher/"]
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: remove unused dependencies, update mypy config"
```

### Task 5.4: Run global ruff cleanup

**Files:**
- All `.py` files

- [ ] **Step 1: Run ruff check --fix**

Run: `ruff check --fix .`
Expected: No errors or fixed

- [ ] **Step 2: Run ruff format**

Run: `ruff format .`
Expected: No formatting errors

- [ ] **Step 3: Run tests to verify**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "style: ruff auto-fix and format"
```

---

## Phase 6: Polish

### Task 6.1: Add `clear_backend_registry()` (#7)

**Files:**
- Modify: `app/printing/backends/base.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add clear function to base.py**

```python
def clear_backend_registry() -> None:
    """清除后端注册表（用于测试隔离）"""
    _backend_registry.clear()
```

- [ ] **Step 2: Add conftest fixture**

```python
# In tests/conftest.py
@pytest.fixture(autouse=True)
def clear_backend():
    from app.printing.backends.base import clear_backend_registry
    clear_backend_registry()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add app/printing/backends/base.py tests/conftest.py
git commit -m "fix: add clear_backend_registry for test isolation"
```

### Task 6.2: Fix SSE lock granularity (#8)

**Files:**
- Modify: `app/services/sse_broadcaster.py:82-108`

- [ ] **Step 1: Consolidate lock around publish logic**

```python
def publish(self, event_type: str, data: Any) -> None:
    with self._lock:
        subs = list(self._subscribers.items())

    # Lock-free: iterate snapshot
    for sub_id, q in subs:
        try:
            q.put_nowait((event_type, data))
            with self._lock:
                if sub_id in self._subscribers:  # verify subscriber still exists
                    self._stale_count.pop(sub_id, None)
        except queue.Full:
            with self._lock:
                if sub_id not in self._subscribers:
                    continue
                try:
                    q.get_nowait()
                    q.put_nowait((event_type, data))
                except queue.Empty:
                    pass
                count = self._stale_count.get(sub_id, 0) + 1
                if count >= _STALE_LIMIT:
                    self._subscribers.pop(sub_id, None)
                    self._stale_count.pop(sub_id, None)
                    self._subscribe_time.pop(sub_id, None)
                else:
                    self._stale_count[sub_id] = count

    self._event_bus.publish(event_type, data)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add app/services/sse_broadcaster.py
git commit -m "fix: consolidate SSE publish lock to prevent subscriber race"
```

### Task 6.3: Rename `drain()` → `wait_stop()` (#9)

**Files:**
- Modify: `app/printing/worker_pool.py:51-65`

- [ ] **Step 1: Rename method**

```python
def wait_stop(self, timeout: float = 30.0) -> None:
    """等待工作线程全部退出"""
    if not self._executor:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        running = sum(1 for f in self._futures if not f.done())
        if running == 0:
            break
        time.sleep(0.5)
    self.stop()
```

- [ ] **Step 2: Find and update all callers**

Search: `worker_pool.drain` → replace with `worker_pool.wait_stop`

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "refactor: rename drain() to wait_stop() in worker_pool"
```

### Task 6.4: Minor fixes (#10, #11)

**Files:**
- Modify: `app/routes/system.py:log_file_read` (encoding fix)

- [ ] **Step 1: Fix log file encoding** (already done in Task 3.2 with `errors='replace'`)

- [ ] **Step 2: Add cancel warning in image.py**

```python
def cancel(self, job_id, _info):
    pdf_info = self._pdf_backend.get_active_job(job_id)
    if pdf_info:
        return self._pdf_backend.cancel(job_id, pdf_info)
    logger.warning(f'无法取消 {job_id}: PdfBackend 尚未开始打印')
    return False
```

- [ ] **Step 3: Commit**

```bash
git add app/printing/backends/image.py
git commit -m "fix: add cancel window warning in ImageBackend"
```

### Task 6.5: GUI/Launcher polish

**Files:**
- Modify: `launcher/__init__.py` — dataclass for _LifespanRef

- [ ] **Step 1: Convert _LifespanRef to dataclass**

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class _LifespanRef:
    config: Optional['Config'] = None
    printer_monitor: Optional[Any] = None
    heartbeat: Optional[Any] = None
    worker_pool: Optional[Any] = None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add launcher/__init__.py
git commit -m "refactor: convert _LifespanRef to dataclass"
```

---

## Phase 7: CI & Testing

### Task 7.1: Fix GitHub CI configuration

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Fix mypy path**

```yaml
# Change line 37:
# From: mypy app/ console/
# To:   mypy app/ gui/ launcher/
```

- [ ] **Step 2: Fix launcher/ path exclusion**

Remove `launcher/**` from the `paths-ignore` list on the `push` and `pull_request` triggers (or move it to only exclude from lint, not from test/build).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: fix stale mypy path and launcher exclusion"
```

### Task 7.2: Add HTTP client lifecycle tests

**Files:**
- Create: `tests/test_http_client_lifecycle.py`

- [ ] **Step 1: Write test**

```python
"""测试 HTTP 客户端生命周期管理"""

import httpx
import pytest


def test_notifier_with_injected_client():
    """验证注入的 httpx.Client 可被正确传递和关闭"""
    from app.services.notifications.bark import BarkNotifier
    client = httpx.Client()
    notifier = BarkNotifier({"notify_channel": "bark", "bark_key": "test", "bark_server": "https://api.day.app"}, client=client)
    assert notifier._http is client
    client.close()


def test_notifier_creates_default_client():
    """验证未传入 client 时自动创建"""
    from app.services.notifications.bark import BarkNotifier
    notifier = BarkNotifier({"notify_channel": "disabled", "bark_key": "", "bark_server": "https://api.day.app"})
    assert notifier._http is not None
    assert isinstance(notifier._http, httpx.Client)
    notifier._http.close()
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_http_client_lifecycle.py -v`
Expected: Both tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_http_client_lifecycle.py
git commit -m "test: add HTTP client lifecycle tests"
```

### Task 7.3: Add queue dedup tests

**Files:**
- Create: `tests/test_job_queue_dedup.py`

- [ ] **Step 1: Write test**

```python
"""测试任务队列去重"""

from unittest.mock import MagicMock
import pytest


def test_recover_stuck_jobs_does_not_duplicate():
    """验证 recover_stuck_jobs 不会把已在队列中的任务重复入队"""
    from app.printing.job_queue import JobQueue

    repo = MagicMock()
    repo.get_jobs_by_status.return_value = [
        {'id': 'job-1', 'created_at': '2024-01-01T00:00:00', 'filename': 'test.pdf'}
    ]

    q = JobQueue(repo)
    q.add_job('test.pdf', '/tmp/test.pdf', source='test')
    # job-1 is in queue now; recovery should skip it
    q.recover_stuck_jobs()

    # Queue should still only have 1 item (the original)
    assert q.queue_size() == 1
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_job_queue_dedup.py -v`
Expected: Test passes

- [ ] **Step 3: Commit**

```bash
git add tests/test_job_queue_dedup.py
git commit -m "test: add queue dedup test for recover_stuck_jobs"
```

### Task 7.4: Add GUI event bridge tests

**Files:**
- Create: `tests/gui/test_event_bridge.py`

- [ ] **Step 1: Write test**

```python
"""测试 EventBridge 信号桥接"""

from unittest.mock import MagicMock
import pytest


class TestEventBridge:
    def test_signal_emission(self):
        """验证 EventBus 事件触发 Qt 信号"""
        from gui.event_bridge import EventBridge
        from PySide6.QtCore import QObject

        bus = MagicMock()
        bus.on = MagicMock()

        parent = QObject()
        bridge = EventBridge(bus, parent)

        # Verify listeners were registered
        assert bus.on.call_count >= 1  # at least job_status
```

- [ ] **Step 2: Run test**

Run: `pytest tests/gui/test_event_bridge.py -v -x`
Expected: Test passes (may need `--qt-api=pyside6` or skip on non-X11)

- [ ] **Step 3: Commit**

```bash
git add tests/gui/test_event_bridge.py
git commit -m "test: add EventBridge signal emission test"
```

### Task 7.5: Run full test suite and verify

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short --cov=app --cov-report=term-missing:skip-covered`
Expected: All tests pass, coverage >= 65%

- [ ] **Step 2: Run mypy**

Run: `mypy app/ gui/ launcher/`
Expected: No errors, or only expected ignore_missing_imports

- [ ] **Step 3: Run ruff**

Run: `ruff check . && ruff format --check .`
Expected: No errors

- [ ] **Step 4: Final commit**

```bash
git add -u
git commit -m "chore: final cleanup and verification"
```
