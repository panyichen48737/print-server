"""后台守护进程 — 无界面运行服务器"""
import os
import sys
import json
import ssl
import atexit
import argparse
import threading
from pathlib import Path

# 确保在项目根目录
if not getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
else:
    os.chdir(os.path.dirname(os.path.abspath(sys.executable)))

from app.config import Config, setup_logging
from app import bootstrap


def write_status(status, **extra):
    """写入 JSON 状态文件供 TUI 读取"""
    from app._paths import app_root
    f = Path(app_root()) / 'logs' / 'daemon.json'
    try:
        data = {'status': status, 'pid': os.getpid(), **extra}
        f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def _health_check_loop(app, config, logger):
    """Background thread that self-polls the health endpoint. 3 failures -> os._exit(1) (nssm restarts)."""
    import urllib.request
    import ssl as ssl_module
    import time
    from pathlib import Path
    from app._paths import app_root

    port = config.get('port', 5000)
    consecutive_failures = 0
    max_failures = 3
    check_interval = 30

    while True:
        time.sleep(check_interval)
        try:
            proto = 'https' if (Path(app_root()) / 'certs' / 'cert.pem').exists() else 'http'
            ctx = None
            if proto == 'https':
                ctx = ssl_module.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl_module.CERT_NONE
            req = urllib.request.Request(
                f'{proto}://127.0.0.1:{port}/api/printers/status',
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
    logger = setup_logging(level=config.log_level)

    write_status('starting')
    logger.info('守护进程启动中...')

    app, queue_mgr, print_engine, printer_monitor = bootstrap(config)
    queue_mgr.start_workers(print_engine)
    printer_monitor.start()

    write_status('running', port=config.get('port', 5000))

    def shutdown():
        logger.info('守护进程关闭中...')
        printer_monitor.stop()
        queue_mgr.shutdown()
        write_status('stopped')

    atexit.register(shutdown)

    port = config.get('port', 5000)

    # 查找证书（开发模式在项目根目录，冻结模式在 EXE 同目录）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    cert_file = os.path.join(script_dir, 'certs', 'cert.pem')
    key_file = os.path.join(script_dir, 'certs', 'key.pem')

    if os.path.isfile(cert_file) and os.path.isfile(key_file):
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(cert_file, key_file)
        logger.info(f'守护进程运行在 https://0.0.0.0:{port} (SSL)')
    else:
        ssl_context = None
        logger.info(f'守护进程运行在 http://0.0.0.0:{port} (无 SSL)')

    # 启动健康检查线程
    health_thread = threading.Thread(target=_health_check_loop, args=(app, config, logger), daemon=True)
    health_thread.start()

    app.run(host='0.0.0.0', port=port, ssl_context=ssl_context, debug=False, threaded=True)


if __name__ == '__main__':
    main()
