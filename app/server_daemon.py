"""后台守护进程 — 无界面运行服务器"""

import argparse
import json
import os
import ssl
import sys
import threading
import time
import urllib.request
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import uvicorn

from app._paths import app_root, persistent_dir
from app.resources import ensure_resources
from app.self_install import ensure_installed

root = app_root()
os.chdir(root)
if not getattr(sys, 'frozen', False) and not getattr(sys, '__compiled__', False):
    sys.path.insert(0, root)

from app.bootstrap import bootstrap  # noqa: E402
from app.config import Config  # noqa: E402
from app.logging import setup_logging  # noqa: E402

_redirect_server = None  # HTTP→HTTPS 重定向服务器


def write_status(status, **extra):
    """写入 JSON 状态文件供 TUI 读取"""
    f = Path(persistent_dir()) / 'logs' / 'daemon.json'
    try:
        data = {'status': status, 'pid': os.getpid(), **extra}
        f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def _find_cert() -> tuple[str | None, str | None]:
    """查找 SSL 证书：certs/ 目录"""
    search_dirs = [
        os.path.join(persistent_dir(), 'resources', 'certs'),
        os.path.join(app_root(), 'certs'),
    ]
    if getattr(sys, 'frozen', False):
        search_dirs.insert(0, os.path.join(os.path.dirname(sys.executable), 'certs'))
    for d in search_dirs:
        cf = os.path.join(d, 'cert.pem')
        kf = os.path.join(d, 'key.pem')
        if os.path.isfile(cf) and os.path.isfile(kf):
            return cf, kf
    return None, None


class _RedirectHandler(BaseHTTPRequestHandler):
    """HTTP→HTTPS 重定向处理器"""

    main_port = 5000  # 会被 _start_redirect_server 覆盖

    def do_GET(self):
        host = self.headers.get('Host', '127.0.0.1').split(':')[0]
        self.send_response(301)
        self.send_header('Location', f'https://{host}:{self.main_port}{self.path}')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(b'')

    do_POST = do_GET  # noqa: N815
    do_PUT = do_GET  # noqa: N815
    do_DELETE = do_GET  # noqa: N815
    do_HEAD = do_GET  # noqa: N815
    do_OPTIONS = do_GET  # noqa: N815

    def log_message(self, fmt, *args):
        pass  # 静默


def _start_redirect_server(
    main_port: int, redirect_port: int | None = None, logger=None
) -> HTTPServer | None:
    """启动 HTTP 重定向服务器（301 → HTTPS）"""
    try:
        rp = redirect_port if redirect_port and redirect_port > 0 else main_port + 1
        _RedirectHandler.main_port = main_port
        server = HTTPServer(('0.0.0.0', rp), _RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f'HTTP 重定向服务运行在 http://0.0.0.0:{rp} → https://0.0.0.0:{main_port}')
        return server
    except Exception as e:
        logger.warning(f'HTTP 重定向服务启动失败: {e}')
        return None


def _health_check_loop(app, config, logger):
    port = config.get('port', 5000)
    use_ssl = config.get('ssl_enabled', False)
    cert_file, _ = _find_cert()
    proto = 'https' if (use_ssl and cert_file) else 'http'
    ctx = None
    if use_ssl and cert_file:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    consecutive_failures = 0
    max_failures = 3
    check_interval = 30

    while True:
        time.sleep(check_interval)
        try:
            req = urllib.request.Request(
                f'{proto}://127.0.0.1:{port}/api/health',
                method='GET',
                headers={'Connection': 'close'},
            )
            urllib.request.urlopen(req, timeout=5, context=ctx)
            consecutive_failures = 0
        except Exception:
            consecutive_failures += 1
            logger.warning(f'健康检查失败 ({consecutive_failures}/{max_failures})')
            if consecutive_failures >= max_failures:
                logger.critical('健康检查连续失败，触发优雅关闭')
                write_status('crashed')
                server = getattr(app.state, '_server', None)
                if server:
                    server.should_exit = True
                return


def main():
    global _uvicorn_server

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--server-daemon', action='store_true', help='以守护进程模式运行（冻结 EXE 入口）'
    )
    parser.parse_known_args()

    # Windows 命名互斥体：防止启动多个守护进程实例
    import ctypes

    mutex_name = 'iOSPrintServerDaemon'
    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, mutex_name)
    if not mutex:
        print('[FATAL] 无法创建互斥体')
        sys.exit(1)
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.kernel32.CloseHandle(mutex)
        print('[FATAL] 守护进程已在运行')
        sys.exit(1)

    config = Config()
    logger = setup_logging(level=config.get('log_level', 'INFO'))

    # 自安装：复制到专属目录并创建开始在菜单
    if not ensure_installed():
        sys.exit(0)

    write_status('starting')
    logger.info('守护进程启动中...')

    # 释放内嵌资源（证书、nssm 等）
    ensure_resources()

    # 定义 FastAPI lifespan，处理优雅关闭
    @asynccontextmanager
    async def server_lifespan(app):
        write_status('running', port=config.get('port', 5000), ssl=config.get('ssl_enabled', False))
        app.state._server = server
        yield
        logger.info('守护进程关闭中...')
        config.stop_watcher()
        printer_monitor.stop()
        heartbeat.stop()
        worker_pool.stop()
        write_status('stopped')

    app, _, worker_pool, _, printer_monitor, heartbeat = bootstrap(config, lifespan=server_lifespan)
    printer_monitor.start()

    port = config.get('port', 5000)

    cert_file, key_file = _find_cert()

    # 启动健康检查线程
    health_thread = threading.Thread(
        target=_health_check_loop, args=(app, config, logger), daemon=True
    )
    health_thread.start()

    # 使用 uvicorn.Server 以便通过 should_exit 触发优雅关闭
    uvicorn_config = uvicorn.Config(
        app,
        host='0.0.0.0',
        port=port,
        log_level='info',
        access_log=False,
    )

    use_ssl = config.get('ssl_enabled', False) and cert_file and key_file
    if use_ssl:
        uvicorn_config.ssl_certfile = cert_file
        uvicorn_config.ssl_keyfile = key_file
        logger.info(f'守护进程运行在 https://0.0.0.0:{port} (SSL)')
        # 启动 HTTP→HTTPS 重定向服务器
        global _redirect_server
        redirect_port = config.get('redirect_port', 0)
        _redirect_server = _start_redirect_server(port, redirect_port, logger)
    else:
        if config.get('ssl_enabled', False):
            logger.warning('SSL 已启用但未找到证书文件（cert.pem / key.pem），回退到 HTTP')
        logger.info(f'守护进程运行在 http://0.0.0.0:{port} (无 SSL)')

    server = uvicorn.Server(uvicorn_config)
    server.run()

    logger.info('守护进程已完全关闭')


if __name__ == '__main__':
    main()
