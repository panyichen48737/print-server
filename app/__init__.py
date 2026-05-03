import os
import logging
from flask import Flask
from app._paths import app_root, ensure_dir


def create_app():
    from app._paths import data_root
    dr = data_root()
    app = Flask(__name__,
                static_folder=os.path.join(dr, 'app', 'static'),
                template_folder=os.path.join(dr, 'app', 'templates'))

    # Register blueprints
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Ensure directories exist
    ensure_dir(app_root(), 'jobs')
    ensure_dir(app_root(), 'logs')

    return app


def bootstrap(config):
    """初始化所有服务并返回 (app, queue_mgr, print_engine) 元组
    注意：不启动 worker 线程，由调用方控制启停"""
    logger = logging.getLogger('print_server')

    from app.services.queue_manager import QueueManager
    from app.services.print_engine import PrintEngine
    from app.services.dingtalk import DingTalk

    app = create_app()
    dingtalk = DingTalk(config)
    queue_mgr = QueueManager(config)
    print_engine = PrintEngine(
        config,
        dingtalk=dingtalk,
        excel_lock=queue_mgr.excel_lock(),
        ppt_lock=queue_mgr.ppt_lock()
    )

    app.config['queue_manager'] = queue_mgr
    app.config['app_config'] = config
    app.config['dingtalk'] = dingtalk
    app.config['MAX_CONTENT_LENGTH'] = config.max_file_size_mb * 1024 * 1024

    queue_mgr.cleanup_old_jobs()

    return app, queue_mgr, print_engine
