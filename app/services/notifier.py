from abc import ABC, abstractmethod


class Notifier(ABC):
    """通知服务抽象接口"""

    @abstractmethod
    def send_notification(self, title: str, message: str, level: str = 'info') -> None:
        ...

    @abstractmethod
    def notify_job_completed(self, filename: str, time_str: str) -> None:
        ...

    @abstractmethod
    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None:
        ...

    @abstractmethod
    def notify_job_cancelled(self, filename: str, time_str: str) -> None:
        ...
