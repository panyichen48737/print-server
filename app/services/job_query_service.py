"""任务查询服务：只读查询的薄封装，包装 JobRepository 与队列大小"""
from typing import Any


class JobQueryService:
    def __init__(self, repo: Any, queue_manager: Any = None) -> None:
        self._repo = repo
        self._queue_manager = queue_manager

    def get_job(self, job_id: str) -> Any:
        return self._repo.get_job(job_id)

    def list_jobs(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        return self._repo.get_jobs(status, search, limit, offset)

    def get_stats(self) -> Any:
        return self._repo.get_stats()

    def count_jobs(self, status: str | None = None, search: str | None = None) -> int:
        return self._repo.count_jobs(status, search)

    def get_queue_size(self) -> int:
        if self._queue_manager:
            return self._queue_manager.queue_size()
        return 0
