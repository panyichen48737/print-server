"""心跳检测模块 — 定期清理过期任务 + 恢复卡住的任务"""
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
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
        self._executor = ThreadPoolExecutor(max_workers=1)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.debug('心跳检测已启动')

    def stop(self) -> None:
        self._stop_evt.set()
        self._executor.shutdown(wait=False)
        logger.debug('心跳检测已停止')

    def _run_with_timeout(self, fn, name, timeout=10):
        """在线程池中执行函数，超时自动放弃"""
        future = self._executor.submit(fn)
        try:
            future.result(timeout=timeout)
        except TimeoutError:
            logger.warning(f'心跳 {name} 执行超时 (>={timeout}s)，已跳过')
        except Exception as e:
            logger.warning(f'心跳 {name} 异常: {e}')

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
