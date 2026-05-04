"""后台守护进程 — 无界面运行服务器"""
import os
import sys
import json
import ssl
import argparse
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from app._paths import app_root

root = app_root()
os.chdir(root)
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, root)

from app.config import Config, setup_logging
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
    import urllib.request
    import time
    from app._paths import app_root

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
                logger.critical('健康检查连续失败，进程退出')
                write_status('crashed')
                os._exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-daemon', action='store_true',
                        help='以守护进程模式运行（冻结 EXE 入口）')
    parser.parse_known_args()

    config = Config()
    logger = setup_logging(level=config.schema.log_level)

    write_status('starting')
    logger.info('守护进程启动中...')

    # 定义 FastAPI lifespan，处理优雅关闭
    @asynccontextmanager
    async def server_lifespan(app):
        write_status('running', port=config.get('port', 5000))
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
    health_thread = threading.Thread(target=_health_check_loop, args=(app, config, logger), daemon=True)
    health_thread.start()

    if os.path.isfile(cert_file) and os.path.isfile(key_file):
        logger.info(f'守护进程运行在 https://0.0.0.0:{port} (SSL)')
        uvicorn.run(app, host='0.0.0.0', port=port,
                    ssl_certfile=cert_file, ssl_keyfile=key_file,
                    log_level='info', access_log=False)
    else:
        logger.info(f'守护进程运行在 http://0.0.0.0:{port} (无 SSL)')
        uvicorn.run(app, host='0.0.0.0', port=port,
                    log_level='info', access_log=False)


if __name__ == '__main__':
    main()
