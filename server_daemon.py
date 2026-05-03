"""后台守护进程 — 无界面运行服务器"""
import os
import sys
import json
import ssl
import atexit
import argparse
from pathlib import Path

# 确保在项目根目录
if not getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
else:
    os.chdir(os.path.dirname(os.path.abspath(sys.executable)))

from app.config import Config, setup_logging
from app import bootstrap, socketio


def write_status(status, **extra):
    """写入 JSON 状态文件供 TUI 读取"""
    from app._paths import app_root
    f = Path(app_root()) / 'logs' / 'daemon.json'
    try:
        data = {'status': status, 'pid': os.getpid(), **extra}
        f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server-daemon', action='store_true',
                        help='以守护进程模式运行（冻结 EXE 入口）')
    parser.parse_known_args()

    config = Config()
    logger = setup_logging(level=config.log_level)

    write_status('starting')
    logger.info('守护进程启动中...')

    app, queue_mgr, print_engine, printer_monitor, _ = bootstrap(config)
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

    socketio.run(app, host='0.0.0.0', port=port, ssl_context=ssl_context, debug=False)


if __name__ == '__main__':
    main()
