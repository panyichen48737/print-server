"""服务装配：初始化所有服务并组装 app"""

from loguru import logger

from app.config import Config
from app import create_app


def bootstrap(config: Config, lifespan=None):
    """初始化所有服务并返回 (app, queue_mgr, print_engine, printer_monitor)"""

    from app.printing.queue_manager import QueueManager
    from app.printing.engine import PrintEngine
    from app.printing.repository import JobRepository
    from app.services.dingtalk import DingTalk
    from app.services.printer_monitor import PrinterMonitor
    from app.services.bark import BarkNotifier
    from app.services.print_service import PrintService
    from app.services.job_query_service import JobQueryService
    from app.services.printer_discovery_service import PrinterDiscoveryService

    app = create_app(lifespan=lifespan)

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
    broadcaster = app.state.sse
    logger.add(LogBroadcaster(broadcaster), format='{message}', level='INFO')

    from app.services.event_bus import EventBus
    event_bus = EventBus(broadcaster)

    repo = JobRepository()
    queue_mgr = QueueManager(config, repo, event_bus=event_bus, notifier=notifier)
    print_engine = PrintEngine(
        config,
        dingtalk=dingtalk,
        excel_lock=queue_mgr.excel_lock(),
        ppt_lock=queue_mgr.ppt_lock()
    )
    printer_monitor = PrinterMonitor(broadcaster=broadcaster)

    print_service = PrintService(config, queue_mgr, event_bus, notifier)
    job_query = JobQueryService(repo, queue_manager=queue_mgr)
    printer_discovery = PrinterDiscoveryService(printer_monitor)

    # Register on app.state instead of app.config
    app.state.queue_manager = queue_mgr
    app.state.app_config = config
    app.state.dingtalk = dingtalk
    app.state.bark = bark
    app.state.printer_monitor = printer_monitor
    app.state.sse_broadcaster = broadcaster
    app.state.print_service = print_service
    app.state.job_query = job_query
    app.state.printer_discovery = printer_discovery

    queue_mgr.cleanup_old_jobs()

    return app, queue_mgr, print_engine, printer_monitor
