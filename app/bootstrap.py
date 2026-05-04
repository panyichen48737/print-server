"""服务装配：初始化所有服务并组装 app"""

import logging

from app.config import Config
from app import create_app


def bootstrap(config: Config):
    """初始化所有服务并返回 (app, queue_mgr, print_engine, printer_monitor) 元组"""
    logger = logging.getLogger('print_server')

    from app.printing.queue_manager import QueueManager
    from app.printing.engine import PrintEngine
    from app.services.dingtalk import DingTalk
    from app.services.printer_monitor import PrinterMonitor
    from app.services.bark import BarkNotifier

    app = create_app()

    broadcaster = app.extensions['sse']

    channel = config.get('notify_channel', 'disabled')
    dingtalk = None
    bark = None
    notifier = None
    if channel == 'dingtalk':
        dingtalk = DingTalk(config)
        notifier = dingtalk
    elif channel == 'bark':
        bark = BarkNotifier(config)
        notifier = bark

    # 日志实时推送
    from app.services.log_broadcaster import LogBroadcaster
    logging.getLogger('print_server').addHandler(LogBroadcaster(broadcaster))

    queue_mgr = QueueManager(config, broadcaster=broadcaster, notifier=notifier)
    print_engine = PrintEngine(
        config,
        dingtalk=dingtalk,
        excel_lock=queue_mgr.excel_lock(),
        ppt_lock=queue_mgr.ppt_lock()
    )
    printer_monitor = PrinterMonitor(broadcaster=broadcaster)

    app.config['queue_manager'] = queue_mgr
    app.config['app_config'] = config
    app.config['dingtalk'] = dingtalk
    app.config['bark'] = bark
    app.config['printer_monitor'] = printer_monitor
    app.config['sse_broadcaster'] = broadcaster
    app.config['MAX_CONTENT_LENGTH'] = config.max_file_size_mb * 1024 * 1024

    queue_mgr.cleanup_old_jobs()

    return app, queue_mgr, print_engine, printer_monitor
