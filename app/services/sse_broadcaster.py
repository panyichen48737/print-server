"""SSE 广播器 — 线程安全的发布/订阅 + 本地事件监听"""
import queue
import threading
import uuid
from typing import Any, Callable

from loguru import logger


_STALE_LIMIT = 3


class SSEBroadcaster:
    """多通道事件广播器。支持 SSE 推送 + 本地 listener 两种订阅方式。"""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: dict[str, queue.Queue] = {}
        self._stale_count: dict[str, int] = {}
        self._listeners: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    # ── 本地事件监听（替代 EventBus.on）──

    def on(self, event_type: str, handler: Callable) -> None:
        """注册本地事件监听器"""
        self._listeners.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        """注销本地事件监听器"""
        self._listeners[event_type] = [h for h in self._listeners.get(event_type, []) if h is not handler]

    # ── SSE 订阅 ──

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

        # 本地事件监听
        for handler in self._listeners.get(event_type, []):
            try:
                handler(data)
            except Exception:
                logger.exception(f'事件监听器异常 ({event_type})')

def init_app(app: Any, maxsize: int = 100) -> SSEBroadcaster:
    """初始化 SSE 广播器并注册到 app.state"""
    broadcaster = SSEBroadcaster(maxsize=maxsize)
    app.state.sse = broadcaster
    return broadcaster
