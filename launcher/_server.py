"""Server lifecycle management — uvicorn in background thread (shared by launcher & GUI)."""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

from loguru import logger

from app.core._paths import app_root, persistent_dir


def _find_cert(config) -> tuple[str | None, str | None]:
    """查找 SSL 证书：certs/ 目录"""
    search_dirs = [
        persistent_dir() / 'resources' / 'certs',
        app_root() / 'certs',
    ]
    if getattr(sys, 'frozen', False):
        search_dirs.insert(0, Path(sys.executable).parent / 'certs')
    for d in search_dirs:
        cf = d / 'cert.pem'
        kf = d / 'key.pem'
        if cf.is_file() and kf.is_file():
            return str(cf), str(kf)
    return None, None


def _port_listening(host: str, port: int) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex((host, port)) == 0
    except Exception:
        return False


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

    def start(self, app, config) -> bool:
        if self.is_running:
            return True

        self._app = app
        self._config = config
        self._port = config.get('port', 5000)

        cert_file, key_file = _find_cert(config)
        self._ssl = bool(cert_file and key_file and config.get('ssl_enabled', False))

        self._thread = threading.Thread(
            target=self._run_uvicorn,
            args=(cert_file, key_file),
            daemon=True,
        )
        self._thread.start()

        # 通过端口连接检测服务器就绪（最长 30 秒）
        for _ in range(300):
            if _port_listening('127.0.0.1', self._port):
                self._started.set()
                logger.info(f'服务器就绪（端口 {self._port}）')
                break
            time.sleep(0.1)

        return self._started.is_set()

    def stop(self) -> None:
        if self.server:
            self.server.should_exit = True
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

        # uvicorn 默认日志配置在 sys.stderr=None 时崩溃（PyInstaller）
        # 我们已用 loguru 接管日志，完全禁用 uvicorn 的日志配置
        log_config = {
            'version': 1,
            'disable_existing_loggers': True,
            'handlers': {},
            'loggers': {},
        }

        uvicorn_config = uvicorn.Config(
            self._app,
            host='0.0.0.0',
            port=self._port,
            log_level='info',
            access_log=False,
            log_config=log_config,
        )
        uvicorn_config.timeout_graceful_shutdown = 5
        if cert_file and key_file and self._config.get('ssl_enabled', False):
            uvicorn_config.ssl_certfile = cert_file
            uvicorn_config.ssl_keyfile = key_file

        self.server = uvicorn.Server(uvicorn_config)
        self.server.run()
