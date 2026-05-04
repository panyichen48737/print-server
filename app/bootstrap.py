"""服务装配：初始化所有服务并组装 app"""

import threading

from loguru import logger

from app.config import Config
from app import create_app
from app.utils import format_time


def bootstrap(config: Config, lifespan=None):
    """初始化所有服务并返回 (app, job_queue, worker_pool, print_engine, printer_monitor)"""

    from app.printing.job_queue import JobQueue
    from app.printing.worker_pool import WorkerPool
    from app.printing.engine import PrintEngine
    from app.printing.repository import JobRepository
    from app.services.dingtalk import DingTalk
    from app.services.printer_monitor import PrinterMonitor
    from app.services.bark import BarkNotifier

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

    # COM 互斥锁 — 确保 Office COM 组件串行访问
    word_lock = threading.Lock()
    excel_lock = threading.Lock()
    ppt_lock = threading.Lock()

    repo = JobRepository()
    job_queue = JobQueue(repo, event_bus=broadcaster)
    worker_pool = WorkerPool(config, event_bus=broadcaster, word_lock=word_lock)
    print_engine = PrintEngine(config, excel_lock=excel_lock, ppt_lock=ppt_lock)
    printer_monitor = PrinterMonitor(broadcaster=broadcaster)

    # 心跳：定时清理过期任务 + 恢复卡住任务
    from app.services.heartbeat import HeartbeatMonitor
    heartbeat = HeartbeatMonitor(
        interval=30,
        cleanup_fn=lambda: job_queue.cleanup_old_jobs(
            config.get('job_retention_days', 30)),
        recover_stuck_fn=job_queue.recover_stuck_jobs,
    )
    heartbeat.start()

    # 事件驱动通知 — 通过 SSEBroadcaster 解耦 Worker 与 Notifier
    if notifier:
        def _on_job_status(data):
            from app.services.notifier import is_print_related_error
            status = data.get('status')
            source = data.get('source', 'api')
            if source == 'ios':
                return
            filename = data.get('filename', '')
            time_str = format_time()
            try:
                if status == 'completed':
                    notifier.notify_job_completed(filename, time_str)
                elif status == 'failed':
                    error = data.get('error', '')
                    if not is_print_related_error(error):
                        return
                    notifier.notify_job_failed(filename, error, time_str)
            except Exception as e:
                logger.warning(f'通知回调异常: {e}')
        broadcaster.on('job_status', _on_job_status)

    # 启动工作线程
    worker_pool.start(print_engine, repo, job_queue)

    # Register on app.state
    app.state.job_queue = job_queue
    app.state.job_repo = repo
    app.state.worker_pool = worker_pool
    app.state.app_config = config
    app.state.print_engine = print_engine
    app.state.dingtalk = dingtalk
    app.state.bark = bark
    app.state.printer_monitor = printer_monitor
    app.state.sse = broadcaster

    job_queue.cleanup_old_jobs(config.get('job_retention_days', 30))

    return app, job_queue, worker_pool, print_engine, printer_monitor, heartbeat
