"""控制台入口 — 单进程架构（直接启动 Flet GUI + uvicorn 同一进程）

用法:
    python -m console    启动 Flet GUI（自动启动后台服务器）
    python -m gui        同上
"""

import contextlib
import ctypes
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger

from app._paths import app_root

sys.path.insert(0, str(app_root()))

from app.config import Config
from app.logging import setup_logging

from ._server import ServerHandle

# ── PID 文件管理 ──

_PID_PATH: Path | None = None


def _pid_file() -> Path:
    global _PID_PATH
    if _PID_PATH is None:
        from app._paths import persistent_dir

        _PID_PATH = persistent_dir() / 'console.pid'
    return _PID_PATH


def _write_pid() -> None:
    _pid_file().parent.mkdir(parents=True, exist_ok=True)
    _pid_file().write_text(str(os.getpid()))
    import atexit

    atexit.register(_cleanup_pid)


def _cleanup_pid() -> None:
    with contextlib.suppress(Exception):
        p = _pid_file()
        if p.exists():
            p.unlink()


def _win_pid_alive(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def _ensure_single_instance() -> None:
    """PID 文件法：防止启动多个实例"""
    p = _pid_file()
    if p.exists():
        try:
            pid = int(p.read_text().strip())
            if _win_pid_alive(pid):
                print(f'服务器已在运行 (PID: {pid})')
                sys.exit(0)
        except (ValueError, OSError):
            pass
    _write_pid()


# ── FastAPI lifespan 延迟绑定 ──


class _LifespanRef:
    def __init__(self):
        self.config = None
        self.printer_monitor = None
        self.heartbeat = None
        self.worker_pool = None


_lifespan_ref = _LifespanRef()


@asynccontextmanager
async def _server_lifespan(_app):
    """FastAPI lifespan — 启动时记录状态，关闭时清理服务"""
    logger.info('服务器启动完成')
    yield
    logger.info('服务器关闭中...')
    ref = _lifespan_ref
    if ref.config:
        ref.config.stop_watcher()
    if ref.printer_monitor:
        ref.printer_monitor.stop()
    if ref.heartbeat:
        ref.heartbeat.stop()
    if ref.worker_pool:
        ref.worker_pool.stop()
    logger.info('服务器已完全关闭')


# ── 服务器启动辅助 ──


def _bootstrap_server() -> tuple:
    """加载配置并 bootstrap 应用，返回 (app, config, worker_pool, printer_monitor, heartbeat)"""
    config = Config()
    setup_logging(level=config.log_level)

    from app.bootstrap import bootstrap
    from app.resources import ensure_resources

    ensure_resources()

    app, _, worker_pool, _, printer_monitor, heartbeat = bootstrap(
        config, lifespan=_server_lifespan
    )
    _lifespan_ref.config = config
    _lifespan_ref.printer_monitor = printer_monitor
    _lifespan_ref.heartbeat = heartbeat
    _lifespan_ref.worker_pool = worker_pool

    return app, config, worker_pool, printer_monitor, heartbeat


def _start_server_background(server_handle: ServerHandle, app, config, printer_monitor) -> None:
    """后台线程：启动服务器及配套服务"""
    printer_monitor.start()
    ok = server_handle.start(app, config)
    if ok:
        logger.info(f'服务器已启动（端口 {server_handle.port}）')
    else:
        logger.error('服务器启动超时')


def _gui_main() -> int:
    """启动 PySide6 GUI（自动启动后台服务器 + 打印机监控）"""
    from gui.app import run_gui

    app, config, _, printer_monitor, _ = _bootstrap_server()
    server_handle = ServerHandle()

    _ensure_single_instance()

    # 后台启动服务器
    threading.Thread(
        target=_start_server_background,
        args=(server_handle, app, config, printer_monitor),
        daemon=True,
    ).start()

    # 启动 PySide6 GUI
    run_gui(app, config, server_handle)

    # GUI 退出后清理
    server_handle.stop()
    _cleanup_pid()
    return 0


def main() -> int | None:
    """入口 — 直接启动 Flet GUI（pyproject.toml scripts 指向此函数）"""
    _gui_main()
    return None


if __name__ == '__main__':
    main()
