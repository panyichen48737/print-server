"""心跳检测模块 — 定期清理过期任务 + 恢复卡住的任务"""
import threading
from datetime import datetime, timedelta
from typing import Any, Callable

from loguru import logger


class HeartbeatMonitor:
    """定期执行清理和恢复操作"""

    def __init__(self, interval: float = 30,
                 cleanup_fn: Callable | None = None,
                 recover_stuck_fn: Callable | None = None) -> None:
        self._interval = interval
        self._cleanup_fn = cleanup_fn
        self._recover_stuck_fn = recover_stuck_fn
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.debug('心跳检测已启动')

    def stop(self) -> None:
        self._stop_evt.set()
        logger.debug('心跳检测已停止')

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                if self._cleanup_fn:
                    self._cleanup_fn()
                if self._recover_stuck_fn:
                    self._recover_stuck_fn()
            except Exception as e:
                logger.error(f'心跳检测异常: {e}')
            self._stop_evt.wait(self._interval)
