"""事件系统 — EventBus（本地监听）+ SSEBroadcaster（远程推送）

EventBus:     on/off/publish    — 服务间本地解耦（JobQueue → Notifier）
SSEBroadcaster: subscribe/unsubscribe/publish    — SSE/WS 远程推送
                同时委托 EventBus 处理本地监听，一次 publish 两端覆盖。
"""
import queue
import threading
import time
import uuid
from typing import Any, Callable

from loguru import logger

_STALE_LIMIT = 3


class EventBus:
    """本地事件监听 — 注册/注销/发布，线程安全"""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    def on(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._listeners.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._listeners[event_type] = [
                h for h in self._listeners.get(event_type, []) if h is not handler
            ]

    def publish(self, event_type: str, data: Any) -> None:
        for handler in list(self._listeners.get(event_type, [])):
            try:
                handler(data)
            except Exception:
                logger.exception(f'事件监听器异常 ({event_type})')


class SSEBroadcaster:
    """远程推送 — SSE/WebSocket 发布/订阅，内部持有 EventBus 处理本地监听"""

    def __init__(self, event_bus: EventBus | None = None, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: dict[str, queue.Queue] = {}
        self._stale_count: dict[str, int] = {}
        self._subscribe_time: dict[str, float] = {}
        self._event_bus = event_bus or EventBus()
        self._lock = threading.Lock()

    # ── 本地监听（委托给 EventBus）──

    def on(self, event_type: str, handler: Callable) -> None:
        self._event_bus.on(event_type, handler)

    def off(self, event_type: str, handler: Callable) -> None:
        self._event_bus.off(event_type, handler)

    # ── 远程订阅 ──

    def subscribe(self) -> tuple[str, queue.Queue]:
        q = queue.Queue(maxsize=self._maxsize)
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[sub_id] = q
            self._subscribe_time[sub_id] = time.monotonic()
        return sub_id, q

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)
            self._stale_count.pop(sub_id, None)
            self._subscribe_time.pop(sub_id, None)

    # ── 发布（远程 + 本地）──

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
                        self._subscribe_time.pop(sub_id, None)
                        logger.warning(
                            f'SSE 订阅者 {sub_id[:8]} 已连续 {_STALE_LIMIT} 次队列满，已移除')
                    else:
                        self._stale_count[sub_id] = count

        self._event_bus.publish(event_type, data)

    def cleanup_idle_subscribers(self, timeout: float = 300) -> int:
        """移除超过 timeout 秒未活动的空闲订阅者。

        线程安全，返回被移除的订阅者数量。
        """
        now = time.monotonic()
        removed = 0
        with self._lock:
            idle_ids = [
                sub_id
                for sub_id, t in self._subscribe_time.items()
                if now - t > timeout
            ]
            for sub_id in idle_ids:
                self._subscribers.pop(sub_id, None)
                self._stale_count.pop(sub_id, None)
                self._subscribe_time.pop(sub_id, None)
                removed += 1
        if removed:
            logger.info(f'已清理 {removed} 个空闲 SSE 订阅者')
        return removed


def init_app(app: Any, maxsize: int = 100) -> SSEBroadcaster:
    """初始化事件系统并注册到 app.state"""
    event_bus = EventBus()
    broadcaster = SSEBroadcaster(event_bus=event_bus, maxsize=maxsize)
    app.state.event_bus = event_bus
    app.state.sse = broadcaster
    return broadcaster
