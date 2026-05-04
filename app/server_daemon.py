"""后台守护进程 — 无界面运行服务器"""
import os
import sys
import json
import ssl
import time
import urllib.request
import argparse
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from app._paths import app_root

root = app_root()
os.chdir(root)
if not getattr(sys, 'frozen', False) and not getattr(sys, '__compiled__', False):
    sys.path.insert(0, root)

from app.config import Config
from app.logging import setup_logging
from app.bootstrap import bootstrap


def write_status(status, **extra):
    """写入 JSON 状态文件供 TUI 读取"""
    f = Path(app_root()) / 'logs' / 'daemon.json'
    try:
        data = {'status': status, 'pid': os.getpid(), **extra}
        f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def _health_check_loop(app, config, logger):
    port = config.get('port', 5000)
    cert_path = Path(app_root()) / 'certs' / 'cert.pem'
    proto = 'https' if cert_path.exists() else 'http'
    ctx = None
    if proto == 'https':
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
                headers={'Connection': 'close'}
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-daemon', action='store_true',
                        help='以守护进程模式运行（冻结 EXE 入口）')
    parser.parse_known_args()

    config = Config()
    logger = setup_logging(level=config.get('log_level', 'INFO'))

    write_status('starting')
    logger.info('守护进程启动中...')

    # 定义 FastAPI lifespan，处理优雅关闭
    @asynccontextmanager
    async def server_lifespan(app):
        write_status('running', port=config.get('port', 5000))
        app.state._server = server
        yield
        logger.info('守护进程关闭中...')
        printer_monitor.stop()
        heartbeat.stop()
        worker_pool.stop()
        write_status('stopped')

    app, job_queue, worker_pool, print_engine, printer_monitor, heartbeat = bootstrap(config, lifespan=server_lifespan)
    printer_monitor.start()

    port = config.get('port', 5000)

    cert_file = os.path.join(root, 'certs', 'cert.pem')
    key_file = os.path.join(root, 'certs', 'key.pem')

    # 启动健康检查线程
    health_thread = threading.Thread(
        target=_health_check_loop, args=(app, config, logger), daemon=True)
    health_thread.start()

    # 使用 uvicorn.Server 以便通过 should_exit 触发优雅关闭
    uvicorn_config = uvicorn.Config(
        app, host='0.0.0.0', port=port,
        log_level='info', access_log=False,
    )
    if os.path.isfile(cert_file) and os.path.isfile(key_file):
        uvicorn_config.ssl_certfile = cert_file
        uvicorn_config.ssl_keyfile = key_file
        logger.info(f'守护进程运行在 https://0.0.0.0:{port} (SSL)')
    else:
        logger.info(f'守护进程运行在 http://0.0.0.0:{port} (无 SSL)')

    server = uvicorn.Server(uvicorn_config)
    server.run()

    logger.info('守护进程已完全关闭')


if __name__ == '__main__':
    main()
