"""事件总线 — 包装 SSEBroadcaster，提供解耦的发布/订阅接口"""

from typing import Any
from app.services.sse_broadcaster import SSEBroadcaster


class EventBus:
    """通用事件总线，业务代码不直接依赖 SSE 实现"""

    def __init__(self, broadcaster: SSEBroadcaster):
        self._broadcaster = broadcaster

    def emit(self, event_type: str, data: Any) -> None:
        """发布事件到所有订阅者"""
        self._broadcaster.publish(event_type, data)

    def subscribe(self) -> tuple[str, Any]:
        """注册新订阅者，返回 (sub_id, Queue)"""
        return self._broadcaster.subscribe()

    def unsubscribe(self, sub_id: str) -> None:
        """注销订阅者"""
        self._broadcaster.unsubscribe(sub_id)
