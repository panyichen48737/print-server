"""心跳检测模块 — 定期清理过期任务 + 恢复卡住的任务"""
import threading
from typing import Callable

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

    def _run_with_timeout(self, fn, name, timeout=10):
        """在子线程中执行函数，超时自动放弃"""
        result = [None]
        error = [None]
        done = threading.Event()

        def wrapper():
            try:
                result[0] = fn()
            except Exception as e:
                error[0] = e
            finally:
                done.set()

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()
        if not done.wait(timeout=timeout):
            logger.warning(f'心跳 {name} 执行超时 (>={timeout}s)，已跳过')
        elif error[0]:
            logger.warning(f'心跳 {name} 异常: {error[0]}')

    def _loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                if self._cleanup_fn:
                    self._run_with_timeout(self._cleanup_fn, '清理', 10)
                if self._recover_stuck_fn:
                    self._run_with_timeout(self._recover_stuck_fn, '恢复', 10)
            except Exception as e:
                logger.error(f'心跳检测异常: {e}')
            self._stop_evt.wait(self._interval)
