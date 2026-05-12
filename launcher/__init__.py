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
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from app.core._paths import app_root

sys.path.insert(0, str(app_root()))

from app.core.config import Config
from app.logging import setup_logging

from ._server import ServerHandle


def _setup_exception_hooks() -> None:
    """全局异常钩子：未捕获异常写入日志 + 弹窗提示"""
    import traceback

    def _write_log(exc_type, exc_value, exc_tb):
        tb_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error(f'未捕获异常:\n{tb_str}')
        return tb_str

    def _show_dialog(title, msg, detail=''):
        """弹窗提示。非主线程用原生 MessageBoxW（避免 Qt 死锁）。"""
        is_main = threading.current_thread() is threading.main_thread()
        if not is_main:
            ctypes.windll.user32.MessageBoxW(
                None, f'{msg}\n\n{detail}' if detail else msg, title, 0x10
            )
            return
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                box = QMessageBox()
                box.setIcon(QMessageBox.Icon.Critical)
                box.setWindowTitle(title)
                box.setText(msg)
                if detail:
                    box.setDetailedText(detail)
                box.exec()
            else:
                ctypes.windll.user32.MessageBoxW(
                    None, f'{msg}\n\n{detail}' if detail else msg, title, 0x10
                )
        except Exception:
            pass

    def _excepthook(exc_type, exc_value, exc_tb):
        tb_str = _write_log(exc_type, exc_value, exc_tb)
        _show_dialog('程序错误', f'{exc_type.__name__}: {exc_value}', tb_str)

    sys.excepthook = _excepthook

    # 线程异常（后端 daemon 线程崩溃时捕获）
    def _thread_excepthook(args):
        tb_str = _write_log(args.exc_type, args.exc_value, args.exc_traceback)
        _show_dialog('线程错误', f'{args.exc_type.__name__}: {args.exc_value}', tb_str)

    threading.excepthook = _thread_excepthook

    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def _qt_msg_handler(msg_type, context, message):
            if msg_type == QtMsgType.QtFatalMsg:
                logger.error(f'Qt Fatal: {message}')
                _excepthook(RuntimeError, RuntimeError(f'Qt: {message}'), None)
            elif msg_type >= QtMsgType.QtCriticalMsg:
                logger.error(f'Qt Critical: {message}')
            elif msg_type >= QtMsgType.QtWarningMsg:
                logger.warning(f'Qt Warning: {message}')

        qInstallMessageHandler(_qt_msg_handler)
    except Exception:
        pass


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
    """Windows 命名互斥体防止多实例。若已有实例：
    - 带 --tray 时静默退出（开机自启/看守服务）
    - 无 --tray 时将已有窗口前置到前台
    """
    with contextlib.suppress(Exception):
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        mutex = kernel32.CreateMutexW(None, False, 'PrintServerLauncher')
        if mutex and kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            if '--tray' not in sys.argv:
                _bring_existing_window_to_front(user32)
            sys.exit(0)

    # PID 文件兜底
    p = _pid_file()
    if p.exists():
        try:
            pid = int(p.read_text().strip())
            handle = kernel32.OpenProcess(0x0400, False, pid)  # PROCESS_QUERY_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                if '--tray' not in sys.argv:
                    _bring_existing_window_to_front(user32)
                sys.exit(0)
        except (ValueError, OSError):
            pass
    _write_pid()


def _bring_existing_window_to_front(user32) -> None:
    """查找现有主窗口并前置到前台"""
    hwnd = user32.FindWindowW(None, 'iOS 云打印服务器')
    if hwnd:
        user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
        user32.SetForegroundWindow(hwnd)


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


def _show_setup_wizard(config, printer_monitor) -> bool:
    """首次启动时显示配置向导，返回 True 表示用户完成了配置"""
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance() or QApplication([])
    from gui.components.setup_wizard import SetupWizard

    wizard = SetupWizard(config, printer_monitor=printer_monitor)
    result = wizard.exec()
    if result:
        logger.info('首次配置已完成')
    else:
        logger.info('用户跳过了首次配置')
    return bool(result)


def _gui_main() -> int:
    """启动 PySide6 GUI（自动启动后台服务器 + 打印机监控）"""
    _ensure_single_instance()  # ← 最先检查，避免冗余初始化

    from gui.app import run_gui

    app, config, _, printer_monitor, _ = _bootstrap_server()

    # 首次启动：显示配置向导
    is_default_key = config.get('api_key') == 'print-server-key-2026'
    if is_default_key:
        _show_setup_wizard(config, printer_monitor)

    # Rebind logger to GUI source for GUI-process logging
    import sys as _sys

    _sys.modules[__name__].logger = logger.bind(source='GUI')

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
    _setup_exception_hooks()
    # 隐藏控制台窗口（Windows GUI 模式）
    with contextlib.suppress(Exception):
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    _gui_main()
    return None


if __name__ == '__main__':
    main()
