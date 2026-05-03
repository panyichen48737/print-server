import os
import sys
import atexit
from app._paths import app_root, ensure_dir

# Ensure project root is in path
sys.path.insert(0, app_root())

from app.config import Config, setup_logging
from app import bootstrap


def main():
    # Load config
    config = Config()

    # Setup logging
    logger = setup_logging(level=config.log_level)
    logger.info('iOS 云打印服务器启动中...')

    # Bootstrap all services
    app, queue_mgr, print_engine = bootstrap(config)

    # Start worker threads (headless mode)
    queue_mgr.start_workers(print_engine)

    # Shutdown handler
    def shutdown():
        logger.info('服务器关闭中...')
        queue_mgr.shutdown()

    atexit.register(shutdown)

    # Check for SSL certs
    ssl_context = None
    root = app_root()
    cert_file = os.path.join(root, 'certs', 'cert.pem')
    key_file = os.path.join(root, 'certs', 'key.pem')
    if os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_context = (cert_file, key_file)
        logger.info('HTTPS 已启用')
    else:
        logger.info('HTTPS 证书未找到，使用 HTTP')

    # Run server
    port = config.get('port', 5000)
    logger.info(f'服务器启动在 http://0.0.0.0:{port}')

    from waitress import serve
    serve(app, host='0.0.0.0', port=port, url_scheme='https' if ssl_context else 'http',
          connection_limit=1000, cleanup_interval=30)


if __name__ == '__main__':
    main()
