"""服务装配：初始化所有服务并组装 app"""

from datetime import datetime

from loguru import logger

from app.config import Config
from app import create_app


def bootstrap(config: Config, lifespan=None):
    """初始化所有服务并返回 (app, job_queue, worker_pool, print_engine, printer_monitor)"""

    from app.printing.job_queue import JobQueue
    from app.printing.worker_pool import WorkerPool
    from app.printing.engine import PrintEngine
    from app.printing.repository import JobRepository
    from app.services.dingtalk import DingTalk
    from app.services.printer_monitor import PrinterMonitor
    from app.services.bark import BarkNotifier
    from app.services.print_service import PrintService
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
    job_queue = JobQueue(repo, event_bus=event_bus)
    worker_pool = WorkerPool(config, event_bus=event_bus)
    print_engine = PrintEngine(
        config,
        dingtalk=dingtalk,
        excel_lock=worker_pool.excel_lock(),
        ppt_lock=worker_pool.ppt_lock()
    )
    printer_monitor = PrinterMonitor(broadcaster=broadcaster)

    # 事件驱动通知 — 通过 EventBus 解耦 Worker 与 Notifier
    if notifier:
        def _on_job_status(data):
            from app.services.notifier import is_print_related_error
            status = data.get('status')
            source = data.get('source', 'api')
            if source == 'ios':
                return
            filename = data.get('filename', '')
            time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                if status == 'completed':
                    notifier.notify_job_completed(filename, time_str)
                elif status == 'failed':
                    error = data.get('error', '')
                    if not is_print_related_error(error):
                        return
                    notifier.notify_job_failed(filename, error, time_str)
            except Exception:
                pass
        event_bus.on('job_status', _on_job_status)

    # 启动工作线程
    worker_pool.start(print_engine, repo, job_queue)

    print_service = PrintService(config, job_queue, event_bus, notifier)
    printer_discovery = PrinterDiscoveryService(printer_monitor)

    # Register on app.state
    app.state.job_queue = job_queue
    app.state.job_repo = repo
    app.state.worker_pool = worker_pool
    app.state.app_config = config
    app.state.dingtalk = dingtalk
    app.state.bark = bark
    app.state.printer_monitor = printer_monitor
    app.state.sse_broadcaster = broadcaster
    app.state.print_service = print_service
    app.state.printer_discovery = printer_discovery

    job_queue.cleanup_old_jobs(config.get('job_retention_days', 30))

    return app, job_queue, worker_pool, print_engine, printer_monitor
