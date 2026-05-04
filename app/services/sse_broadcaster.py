"""SSE 广播器 — 线程安全的发布/订阅单例，替代 flask-socketio"""
import queue
import threading
import uuid
from typing import Any

from loguru import logger


_STALE_LIMIT = 3


class SSEBroadcaster:
    """多通道事件广播器。每个 subscriber 有一个独立的 Queue，publish 非阻塞。"""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: dict[str, queue.Queue] = {}
        self._stale_count: dict[str, int] = {}
        self._lock = threading.Lock()

    def subscribe(self) -> tuple[str, queue.Queue]:
        q = queue.Queue(maxsize=self._maxsize)
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[sub_id] = q
        return sub_id, q

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)
            self._stale_count.pop(sub_id, None)

    def publish(self, event_type: str, data: Any) -> None:
        with self._lock:
            subs = list(self._subscribers.items())
        for sub_id, q in subs:
            try:
                q.put_nowait((event_type, data))
                with self._lock:
                    self._stale_count.pop(sub_id, None)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait((event_type, data))
                    logger.warning(f'SSE 订阅者 {sub_id[:8]} 队列已满，丢弃旧事件')
                except queue.Empty:
                    pass
                with self._lock:
                    count = self._stale_count.get(sub_id, 0) + 1
                    if count >= _STALE_LIMIT:
                        self._subscribers.pop(sub_id, None)
                        self._stale_count.pop(sub_id, None)
                        logger.warning(f'SSE 订阅者 {sub_id[:8]} 已连续 {_STALE_LIMIT} 次队列满，已移除')
                    else:
                        self._stale_count[sub_id] = count

    def remove_stale_subscribers(self) -> int:
        """扫描并移除累积满队列次数达到阈值的订阅者"""
        removed = 0
        with self._lock:
            for sub_id in list(self._subscribers.keys()):
                count = self._stale_count.get(sub_id, 0)
                if count >= _STALE_LIMIT:
                    self._subscribers.pop(sub_id, None)
                    self._stale_count.pop(sub_id, None)
                    removed += 1
        if removed:
            logger.info(f'移除 {removed} 个过期 SSE 订阅者')
        return removed

    def cleanup(self) -> int:
        """清理过期订阅者，返回移除数量"""
        return self.remove_stale_subscribers()


def init_app(app: Any, maxsize: int = 100) -> SSEBroadcaster:
    """初始化 SSE 广播器并注册到 app.state"""
    broadcaster = SSEBroadcaster(maxsize=maxsize)
    app.state.sse = broadcaster
    return broadcaster
