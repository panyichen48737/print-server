"""打印后端抽象基类 + 插件注册机制"""

from abc import ABC, abstractmethod
from typing import Any

_backend_registry: dict[str, type['PrinterBackend']] = {}


def register(*extensions: str):
    """类装饰器：按文件扩展名注册后端"""

    def decorator(cls):
        cls._supported_extensions = set(extensions)
        for ext in extensions:
            _backend_registry[ext.lower()] = cls
        return cls

    return decorator


def discover_backends() -> dict[str, type['PrinterBackend']]:
    """返回 {扩展名: 后端类} 映射"""
    return dict(_backend_registry)


class PrinterBackend(ABC):
    """打印机后端接口"""

    _supported_extensions: set[str] = set()

    @abstractmethod
    def print_file(
        self, filepath: str, job_id: str, print_params: dict[str, Any], lock=None
    ) -> bool:
        """执行打印，成功返回 True，失败抛异常"""
        ...

    @abstractmethod
    def cancel(self, job_id: str, info: dict) -> bool:
        """取消正在打印的任务"""
        ...
