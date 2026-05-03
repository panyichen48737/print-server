"""iOS 云打印服务器 — HTTP 入口（eventlet + SocketIO）"""
import os
import sys
import atexit
from app._paths import app_root, ensure_dir

sys.path.insert(0, app_root())

from app.config import Config, setup_logging
from app import bootstrap, socketio


def main():
    config = Config()
    logger = setup_logging(level=config.log_level)
    logger.info('iOS 云打印服务器启动中...')

    app, queue_mgr, print_engine, printer_monitor, _ = bootstrap(config)
    queue_mgr.start_workers(print_engine)
    printer_monitor.start()

    def shutdown():
        logger.info('服务器关闭中...')
        printer_monitor.stop()
        queue_mgr.shutdown()

    atexit.register(shutdown)

    port = config.get('port', 5000)
    logger.info(f'服务器启动在 http://0.0.0.0:{port}')
    socketio.run(app, host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    main()
