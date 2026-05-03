"""SSE 广播器 — 线程安全的发布/订阅单例，替代 flask-socketio"""
import queue
import threading
import uuid


class SSEBroadcaster:
    """多通道事件广播器。每个 subscriber 有一个独立的 Queue，publish 非阻塞。"""

    def __init__(self, maxsize=100):
        self._maxsize = maxsize
        self._subscribers = {}
        self._lock = threading.Lock()

    def subscribe(self):
        """注册新订阅者，返回 (sub_id, Queue)"""
        q = queue.Queue(maxsize=self._maxsize)
        sub_id = str(uuid.uuid4())
        with self._lock:
            self._subscribers[sub_id] = q
        return sub_id, q

    def unsubscribe(self, sub_id):
        """注销订阅者"""
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def publish(self, event_type, data):
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
                except queue.Empty:
                    pass


_broadcaster = None
_broadcaster_lock = threading.Lock()


def get_broadcaster(maxsize=100):
    """获取模块级单例"""
    global _broadcaster
    if _broadcaster is None:
        with _broadcaster_lock:
            if _broadcaster is None:
                _broadcaster = SSEBroadcaster(maxsize=maxsize)
    return _broadcaster


def init_app(app, maxsize=100):
    """初始化 SSE 广播器并注册到 app.extensions"""
    broadcaster = SSEBroadcaster(maxsize=maxsize)
    app.extensions['sse'] = broadcaster
    return broadcaster
