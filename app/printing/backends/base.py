"""打印后端抽象基类"""
from abc import ABC, abstractmethod
from typing import Any


class PrinterBackend(ABC):
    """打印机后端接口"""

    @abstractmethod
    def print_file(self, filepath: str, job_id: str, print_params: dict[str, Any], lock=None) -> bool:
        """执行打印，成功返回 True，失败抛异常"""
        ...

    @abstractmethod
    def cancel(self, job_id: str, info: dict) -> bool:
        """取消正在打印的任务"""
        ...
