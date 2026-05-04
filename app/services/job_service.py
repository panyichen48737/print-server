"""任务服务层 — routes 与 queue_manager 之间的中介"""

from typing import Any

from loguru import logger


class JobService:
    """封装 QueueManager 操作，供 routes 层调用，解耦 Flask 与业务逻辑"""

    def __init__(self, queue_manager: Any, config: Any, printer_monitor: Any = None) -> None:
        self._queue_mgr = queue_manager
        self._config = config
        self._printer_monitor = printer_monitor

    def submit(self, request: Any, *, source: str = 'api') -> Any:
        """提交打印任务"""
        from app.upload_helper import handle_file_upload
        return handle_file_upload(request, self._config, self._queue_mgr, source=source)

    def get_status(self, job_id: str) -> dict | None:
        """查询任务状态，返回 dict 或 None"""
        job = self._queue_mgr.get_job(job_id)
        if not job:
            return None
        result: dict[str, Any] = {'status': job['status'], 'job_id': job['id']}
        if job['status'] == 'failed' and job.get('error_message'):
            result['error'] = job['error_message']
        return result

    def cancel(self, job_id: str) -> Any:
        """取消任务"""
        return self._queue_mgr.cancel_job(job_id)

    def cancel_all_queued(self) -> int:
        """取消所有排队任务"""
        return self._queue_mgr.cancel_all_queued()

    def retry(self, job_id: str) -> Any:
        """重试失败任务"""
        return self._queue_mgr.retry_job(job_id)

    def list_printers(self) -> list[str]:
        """获取打印机列表"""
        return self._queue_mgr.get_printers()

    def get_printer_statuses(self) -> dict[str, Any]:
        """获取打印机实时状态"""
        if self._printer_monitor:
            return self._printer_monitor.get_all_statuses()
        return {}

    def list_jobs(self, status: str | None = None, search: str | None = None,
                  limit: int = 50, offset: int = 0) -> list[dict]:
        """查询任务列表"""
        return self._queue_mgr.get_jobs(status, search, limit, offset)

    def count_jobs(self, status: str | None = None, search: str | None = None) -> int:
        """统计任务数"""
        return self._queue_mgr.count_jobs(status, search)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return self._queue_mgr.get_stats()

    def get_job(self, job_id: str) -> dict | None:
        """获取单个任务详情"""
        return self._queue_mgr.get_job(job_id)
