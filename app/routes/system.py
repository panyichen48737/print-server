"""系统相关路由 — 健康检查、版本、日志、统计"""

import time
from collections import deque
from pathlib import Path

from fastapi import APIRouter, Request

from app.core._paths import log_dir, persistent_dir
from app.core.version import __build_date__, __pyinstaller_version__, __version__

system_router = APIRouter()

_start_time = time.time()


@system_router.get('/health')
async def health(request: Request):
    db_path = Path(persistent_dir()) / 'jobs.db'
    db_size = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
    return {
        'status': 'ok',
        'version': __version__,
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


@system_router.get('/logs')
async def api_logs(_request: Request, lines: int = 50):
    log_file = log_dir() / 'app.log'
    try:
        with open(log_file, encoding='utf-8') as f:
            last_lines = deque(f, maxlen=lines)
        return {'lines': list(last_lines)}
    except FileNotFoundError:
        return {'lines': []}
    except Exception as e:
        return {'lines': [f'[ERROR] 读取日志失败: {e}']}


@system_router.get('/stats')
async def api_stats_json(request: Request):
    stats = request.app.state.job_repo.get_stats()
    stats['daily_counts'] = request.app.state.job_repo.get_daily_counts(7)
    return stats
