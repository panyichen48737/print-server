"""事件总线 — 包装 SSEBroadcaster，提供解耦的发布/订阅接口"""

from app.services.sse_broadcaster import SSEBroadcaster


class EventBus:
    """通用事件总线，业务代码不直接依赖 SSE 实现"""

    def __init__(self, broadcaster: SSEBroadcaster) -> None:
        self._broadcaster = broadcaster
        self._listeners: dict[str, list[callable]] = {}

    def on(self, event_type: str, handler: callable) -> None:
        """注册本地事件监听器"""
        self._listeners.setdefault(event_type, []).append(handler)

    def emit(self, event_type: str, data) -> None:
        """发布事件到所有订阅者 + 本地监听器"""
        try:
            self._broadcaster.publish(event_type, data)
        except Exception:
            pass
        for handler in self._listeners.get(event_type, []):
            try:
                handler(data)
            except Exception:
                pass

    def subscribe(self) -> tuple:
        """注册新订阅者，返回 (sub_id, Queue)"""
        return self._broadcaster.subscribe()

    def unsubscribe(self, sub_id: str) -> None:
        """注销订阅者"""
        self._broadcaster.unsubscribe(sub_id)
