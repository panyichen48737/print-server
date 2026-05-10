"""启动入口 — 单进程架构（直接启动 PySide6 GUI + uvicorn 同一进程）

用法:
    python -m launcher    启动 PySide6 GUI（自动启动后台服务器）
"""

import contextlib
import ctypes
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger

from app.core._paths import app_root

sys.path.insert(0, str(app_root()))

from app.core.config import Config
from app.logging import setup_logging

from ._server import ServerHandle

# ── PID 文件管理 ──

_PID_PATH: Path | None = None


def _pid_file() -> Path:
    global _PID_PATH
    if _PID_PATH is None:
        from app.core._paths import persistent_dir

        _PID_PATH = persistent_dir() / 'launcher.pid'
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


def _ensure_single_instance() -> None:
    """Windows 命名互斥体 + PID 文件双重检测防止多实例"""
    # Windows 命名互斥体（最可靠方式）
    with contextlib.suppress(Exception):
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, "PrintServerLauncher")
        if mutex and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            print('服务器已在运行')
            sys.exit(0)

    # PID 文件兜底
    p = _pid_file()
    if p.exists():
        try:
            pid = int(p.read_text().strip())
            handle = kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                print(f'服务器已在运行 (PID: {pid})')
                sys.exit(0)
        except (ValueError, OSError):
            pass
    _write_pid()


# ── FastAPI lifespan 延迟绑定 ──


from dataclasses import dataclass


@dataclass
class _LifespanRef:
    config: object = None
    printer_monitor: object = None
    heartbeat: object = None
    worker_pool: object = None


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
    # 关闭全局 HTTP 客户端
    http_client = getattr(_app.state, 'http_client', None)
    if http_client:
        with contextlib.suppress(Exception):
            http_client.close()
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
    _ensure_single_instance()  # ← 最先检查，避免冗余初始化

    from gui.app import run_gui

    app, config, _, printer_monitor, _ = _bootstrap_server()
    server_handle = ServerHandle()

    # 后台启动服务器
    threading.Thread(
        target=_start_server_background,
        args=(server_handle, app, config, printer_monitor),
        daemon=True,
    ).start()

    # 启动 PySide6 GUI（阻塞至用户退出）
    run_gui(app, config, server_handle)

    # GUI 退出后清理
    server_handle.stop()
    _cleanup_pid()
    return 0


def main() -> int | None:
    """入口 — 直接启动 PySide6 GUI（pyproject.toml scripts 指向此函数）"""
    # 隐藏控制台窗口（Windows GUI 模式）
    with contextlib.suppress(Exception):
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    _gui_main()
    return None


if __name__ == '__main__':
    main()
