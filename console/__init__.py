"""控制台入口 — 单进程架构（TUI + uvicorn 同一进程）

用法:
    python -m console             启动 TUI（自动启动后台服务器）
    python -m console --headless  仅启动服务器（无界面）
    python -m console --start     --headless 别名
    python -m console --stop      停止服务器
    python -m console --restart   重启服务器
    python -m console --status    查看服务器状态
"""

import argparse
import contextlib
import ctypes
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from loguru import logger

from app._paths import app_root

sys.path.insert(0, str(app_root()))

from app.config import Config
from app.logging import setup_logging

from .autostart import install_autostart, is_autostart_installed, uninstall_autostart

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


# ── TLS 证书查找 ──


def _find_cert() -> tuple[str | None, str | None]:
    """查找 SSL 证书：certs/ 目录"""
    from app._paths import app_root as _app_root, persistent_dir  # noqa: I001

    search_dirs = [
        persistent_dir() / 'resources' / 'certs',
        _app_root() / 'certs',
    ]
    if getattr(sys, 'frozen', False):
        search_dirs.insert(0, Path(sys.executable).parent / 'certs')
    for d in search_dirs:
        cf = d / 'cert.pem'
        kf = d / 'key.pem'
        if cf.is_file() and kf.is_file():
            return str(cf), str(kf)
    return None, None


# ── HTTP→HTTPS 重定向服务器 ──

from http.server import BaseHTTPRequestHandler, HTTPServer  # noqa: E402


class _RedirectHandler(BaseHTTPRequestHandler):
    """HTTP→HTTPS 301 重定向"""

    main_port = 5000

    def do_GET(self):
        host = self.headers.get('Host', '127.0.0.1').split(':')[0]
        self.send_response(301)
        self.send_header('Location', f'https://{host}:{self.main_port}{self.path}')
        self.send_header('Connection', 'close')
        self.end_headers()

    do_POST = do_GET  # noqa: N815
    do_PUT = do_GET  # noqa: N815
    do_DELETE = do_GET  # noqa: N815
    do_HEAD = do_GET  # noqa: N815
    do_OPTIONS = do_GET  # noqa: N815

    def log_message(self, fmt, *args):
        pass


def _start_redirect_server(main_port: int, redirect_port: int | None = None) -> HTTPServer | None:
    """启动 HTTP→HTTPS 重定向服务器（守护线程）"""
    try:
        rp = redirect_port if redirect_port and redirect_port > 0 else main_port + 1
        _RedirectHandler.main_port = main_port
        server = HTTPServer(('0.0.0.0', rp), _RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f'HTTP 重定向服务 http://0.0.0.0:{rp} → https://0.0.0.0:{main_port}')
        return server
    except Exception as e:
        logger.warning(f'HTTP 重定向服务启动失败: {e}')
        return None


# ── 服务器生命周期管理 ──


class ServerHandle:
    """在后台线程中管理 uvicorn.Server 生命周期（单进程，无子进程）"""

    def __init__(self):
        self.server = None  # uvicorn.Server
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._app = None
        self._config = None
        self._port: int | None = None
        self._ssl = False
        self._redirect_server = None

    def start(self, app, config) -> bool:
        if self.is_running:
            return True

        self._app = app
        self._config = config
        self._port = config.get('port', 5000)

        cert_file, key_file = _find_cert()
        self._ssl = bool(cert_file and key_file and config.get('ssl_enabled', False))

        self._thread = threading.Thread(
            target=self._run_uvicorn,
            args=(cert_file, key_file),
            daemon=True,
        )
        self._thread.start()

        # 通过端口连接检测服务器就绪（比轮询 uvicorn.Server.started 更可靠）
        for _ in range(150):
            if self._port_listening('127.0.0.1', self._port):
                self._started.set()
                break
            time.sleep(0.1)

        ready = self._started.is_set()

        if ready and self._ssl:
            redirect_port = config.get('redirect_port', 0)
            self._redirect_server = _start_redirect_server(self._port, redirect_port)

        return ready

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
        if self._redirect_server:
            with contextlib.suppress(Exception):
                self._redirect_server.shutdown()
            self._redirect_server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._started.clear()

    @property
    def is_running(self) -> bool:
        return self._started.is_set()

    @property
    def port(self) -> int | None:
        return self._port

    @property
    def ssl_enabled(self) -> bool:
        return self._ssl

    def _run_uvicorn(self, cert_file: str | None, key_file: str | None) -> None:
        import uvicorn

        uvicorn_config = uvicorn.Config(
            self._app,
            host='0.0.0.0',
            port=self._port,
            log_level='info',
            access_log=False,
        )
        uvicorn_config.timeout_graceful_shutdown = 5
        if cert_file and key_file and self._config.get('ssl_enabled', False):
            uvicorn_config.ssl_certfile = cert_file
            uvicorn_config.ssl_keyfile = key_file

        self.server = uvicorn.Server(uvicorn_config)
        self.server.run()

    @staticmethod
    def _port_listening(host: str, port: int) -> bool:
        """检测端口是否已被监听（TCP 连接检查）"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False


# ── FastAPI lifespan 延迟绑定 ──


class _LifespanRef:
    """在 bootstrap() 之后延迟填充，供 lifespan 关闭时使用"""

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


# ── VT 处理 ──


def _enable_vt_processing() -> None:
    """启用 Windows 控制台 VT 处理（Textual 必需）"""
    if sys.platform != 'win32':
        return
    with contextlib.suppress(Exception):
        kernel32 = ctypes.windll.kernel32
        enable_vt = 0x0004
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | enable_vt)


# ── CLI 入口 ──


def main() -> int | None:
    _enable_vt_processing()

    parser = argparse.ArgumentParser(description='iOS 云打印服务器')
    parser.add_argument('--headless', action='store_true', help='无界面运行服务器')
    parser.add_argument('--gui', action='store_true', help='启动 Flet 图形界面')
    parser.add_argument('--start', action='store_true', help='启动服务器（--headless 别名）')
    parser.add_argument('--stop', action='store_true', help='停止服务器')
    parser.add_argument('--restart', action='store_true', help='重启服务器')
    parser.add_argument('--status', action='store_true', help='查看服务器状态')
    parser.add_argument('--autostart-install', action='store_true', help='注册开机自启')
    parser.add_argument('--autostart-uninstall', action='store_true', help='卸载开机自启')
    args = parser.parse_args()

    # ── 简单命令（无需启动服务器） ──

    if args.gui:
        import flet as ft

        from gui.app import main as gui_main
        ft.run(gui_main)
        return 0

    if args.stop:
        p = _pid_file()
        if p.exists():
            try:
                pid = int(p.read_text().strip())
                if _win_pid_alive(pid):
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(pid)],
                        capture_output=True,
                        timeout=5,
                    )
                    time.sleep(0.5)
                    _cleanup_pid()
                    print('服务器已停止')
                else:
                    _cleanup_pid()
                    print('服务器未运行')
            except (ValueError, OSError):
                print('无法读取 PID 文件')
        else:
            print('服务器未运行')
        return 0

    if args.status:
        cfg = Config()
        port = cfg.get('port', 5000)
        try:
            import urllib.request

            urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3)
            print('状态: 运行中')
        except Exception:
            print('状态: 已停止')
        print(f'端口: {port}')
        print(f'自启: {"已注册" if is_autostart_installed() else "未注册"}')
        return 0

    if args.autostart_install:
        ok, msg = install_autostart()
        print(msg)
        return 0 if ok else 1

    if args.autostart_uninstall:
        ok, msg = uninstall_autostart()
        print(msg)
        return 0 if ok else 1

    # ── 需要完整启动服务器 ──

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

    server_handle = ServerHandle()

    # ── 无界面模式（--headless / --start） ──

    if args.headless or args.start:
        _ensure_single_instance()
        printer_monitor.start()

        def _handle_exit(signum, frame):
            logger.info('收到信号 {}, 正在关闭...', signum)
            server_handle.stop()

        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)

        ok = server_handle.start(app, config)
        if not ok:
            print('服务器启动失败')
            return 1
        proto = 'https' if server_handle.ssl_enabled else 'http'
        print(f'服务器运行在 {proto}://0.0.0.0:{server_handle.port}')
        try:
            while server_handle.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            server_handle.stop()
        return 0

    # ── 重启模式 ──

    if args.restart:
        p = _pid_file()
        if p.exists():
            try:
                pid = int(p.read_text().strip())
                if _win_pid_alive(pid):
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(pid)],
                        capture_output=True,
                        timeout=5,
                    )
                    time.sleep(1)
            except Exception:
                pass
        _cleanup_pid()
        _write_pid()
        printer_monitor.start()
        ok = server_handle.start(app, config)
        if not ok:
            print('重启失败')
            return 1
        print(f'服务器已重启（端口 {server_handle.port}）')
        try:
            while server_handle.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            server_handle.stop()
        return 0

    # ── TUI 模式（默认） ──

    _ensure_single_instance()

    from .log_handler import TUILogHandler

    tui_handler = TUILogHandler()
    logger.add(tui_handler, format='{time:HH:mm:ss} {level} {message}', level='ERROR')

    try:
        from .tui import TUI

        tui = TUI(server_handle=server_handle, app=app, config=config)
        threading.Thread(
            target=_start_server_background,
            args=(server_handle, app, config, printer_monitor),
            daemon=True,
        ).start()
        tui.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback

        error_detail = traceback.format_exc()
        logger.error(f'TUI 启动失败: {e}\n{error_detail}')
        try:
            diag = (
                Path(os.environ.get('APPDATA', '.')) / 'iOSPrintServer' / 'logs' / 'tui_error.log'
            )
            diag.parent.mkdir(parents=True, exist_ok=True)
            diag.write_text(error_detail)
        except Exception:
            pass
        print(f'\nTUI 界面启动失败: {e}')
        print('服务已在后台运行，请访问 Web 管理页面:')
        from .conflicts import get_local_ips

        ips = get_local_ips()
        ip_str = ips[0] if ips else '127.0.0.1'
        proto = 'https' if config.get('ssl_enabled', False) else 'http'
        print(f'  {proto}://{ip_str}:{config.get("port", 5000)}/admin')
        print('\n按 Enter 退出...')
        input()
    finally:
        server_handle.stop()
        _cleanup_pid()

    return None


def _start_server_background(server_handle: ServerHandle, app, config, printer_monitor) -> None:
    """后台线程：启动服务器"""
    printer_monitor.start()
    ok = server_handle.start(app, config)
    if ok:
        logger.info(f'服务器已启动（端口 {server_handle.port}）')
    else:
        logger.error('服务器启动超时')
