"""事件系统 — SSEBroadcaster：本地监听 + SSE/WS 远程推送

SSEBroadcaster: on/off/subscribe/unsubscribe/publish
                一次 publish 覆盖本地监听器和远程订阅者。
"""

import queue
import re
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from loguru import logger

_STALE_LIMIT = 3
_LOG_PATTERN = re.compile(r'^\[([^\]]+)\]\s+\[([^\]]+)\]\s+(.*)')


class SSEBroadcaster:
    """发布/订阅 + 本地监听 — 一次 publish 覆盖 SSE 远程订阅者和本地监听器"""

    def __init__(self, maxsize: int = 100) -> None:
        self._maxsize = maxsize
        self._subscribers: dict[str, queue.Queue] = {}
        self._stale_count: dict[str, int] = {}
        self._subscribe_time: dict[str, float] = {}
        self._listeners: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()

    # ── 本地监听 ──

    def on(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._listeners.setdefault(event_type, []).append(handler)

    def off(self, event_type: str, handler: Callable) -> None:
        with self._lock:
            self._listeners[event_type] = [
                h for h in self._listeners.get(event_type, []) if h is not handler
            ]

    # ── 远程订阅 ──

    def subscribe(self) -> tuple[str, queue.Queue]:
        q: queue.Queue = queue.Queue(maxsize=self._maxsize)
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

        stale_ids: list[str] = []
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
                with self._lock:
                    count = self._stale_count.get(sub_id, 0) + 1
                    if count >= _STALE_LIMIT:
                        stale_ids.append(sub_id)
                    else:
                        self._stale_count[sub_id] = count
            else:
                with self._lock:
                    self._stale_count.pop(sub_id, None)

        if stale_ids:
            with self._lock:
                for sub_id in stale_ids:
                    self._subscribers.pop(sub_id, None)
                    self._stale_count.pop(sub_id, None)
                    self._subscribe_time.pop(sub_id, None)
                    logger.warning(
                        f'SSE 订阅者 {sub_id[:8]} 已连续 {_STALE_LIMIT} 次队列满，已移除'
                    )

        for handler in list(self._listeners.get(event_type, [])):
            try:
                handler(data)
            except Exception:
                logger.exception(f'事件监听器异常 ({event_type})')

    def cleanup_idle_subscribers(self, timeout: float = 300) -> int:
        """移除超过 timeout 秒未活动的空闲订阅者。

        线程安全，返回被移除的订阅者数量。
        """
        now = time.monotonic()
        removed = 0
        with self._lock:
            idle_ids = [sub_id for sub_id, t in self._subscribe_time.items() if now - t > timeout]
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
    broadcaster = SSEBroadcaster(maxsize=maxsize)
    app.state.sse = broadcaster
    return broadcaster


class LogBroadcaster:
    """loguru sink — 将日志推送到 SSE，消息格式需包含 [{extra[source]}] [{level}] 前缀"""

    def __init__(self, broadcaster=None):
        self._broadcaster = broadcaster

    def write(self, message):
        if message.strip() and self._broadcaster:
            msg = message.strip()
            source = 'Server'
            level = 'INFO'
            m = _LOG_PATTERN.match(msg)
            if m:
                source = m.group(1)
                level = m.group(2)
                msg = m.group(3)
            self._broadcaster.publish(
                'log',
                {
                    'message': msg,
                    'level': level,
                    'source': source,
                },
            )
