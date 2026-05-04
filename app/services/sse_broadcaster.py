"""SSE 广播器 — 线程安全的发布/订阅单例，替代 flask-socketio"""
import queue
import threading
import uuid
from typing import Any

from loguru import logger


class SSEBroadcaster:
    """多通道事件广播器。每个 subscriber 有一个独立的 Queue，publish 非阻塞。"""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: dict[str, queue.Queue] = {}
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

    def publish(self, event_type: str, data: Any) -> None:
        with self._lock:
            subs = list(self._subscribers.items())
        for sub_id, q in subs:
            try:
                q.put_nowait((event_type, data))
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait((event_type, data))
                    logger.warning(f'SSE 订阅者 {sub_id[:8]} 队列已满，丢弃旧事件')
                except queue.Empty:
                    pass


def init_app(app: Any, maxsize: int = 100) -> SSEBroadcaster:
    """初始化 SSE 广播器并注册到 app.state"""
    broadcaster = SSEBroadcaster(maxsize=maxsize)
    app.state.sse = broadcaster
    return broadcaster
