"""SSE 广播器 — 线程安全的发布/订阅单例，替代 flask-socketio"""
import queue
import threading
import uuid
import logging
from typing import Any

logger = logging.getLogger('print_server')


class SSEBroadcaster:
    """多通道事件广播器。每个 subscriber 有一个独立的 Queue，publish 非阻塞。"""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers = {}
        self._lock = threading.Lock()

    def subscribe(self) -> tuple[str, queue.Queue]:
        """注册新订阅者，返回 (sub_id, Queue)"""
        q = queue.Queue(maxsize=self._maxsize)
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[sub_id] = q
        return sub_id, q

    def unsubscribe(self, sub_id: str) -> None:
        """注销订阅者"""
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def publish(self, event_type: str, data: Any) -> None:
        """发布事件到所有订阅者（丢弃已满队列，不阻塞）"""
        with self._lock:
            subs = list(self._subscribers.items())
        for sub_id, q in subs:
            try:
                q.put_nowait((event_type, data))
            except queue.Full:
                # 慢客户端：丢弃最旧事件，腾出空间
                try:
                    q.get_nowait()
                    q.put_nowait((event_type, data))
                    logger.warning(f'SSE 订阅者 {sub_id[:8]} 队列已满，丢弃旧事件')
                except queue.Empty:
                    pass


_broadcaster = None
_broadcaster_lock = threading.Lock()


def get_broadcaster(maxsize: int = 100) -> SSEBroadcaster:
    """获取模块级单例"""
    global _broadcaster
    if _broadcaster is None:
        with _broadcaster_lock:
            if _broadcaster is None:
                _broadcaster = SSEBroadcaster(maxsize=maxsize)
    return _broadcaster


def init_app(app, maxsize: int = 100) -> SSEBroadcaster:
    """初始化 SSE 广播器并注册到 app.extensions"""
    broadcaster = SSEBroadcaster(maxsize=maxsize)
    app.extensions['sse'] = broadcaster
    return broadcaster
