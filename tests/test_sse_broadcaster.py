"""测试 SSE 广播器"""

from unittest.mock import MagicMock

import pytest

from app.services.sse_broadcaster import SSEBroadcaster, init_app


class TestSSEBroadcaster:
    """SSE 发布/订阅 + 本地监听"""

    def test_subscribe_returns_queue(self):
        b = SSEBroadcaster()
        sub_id, q = b.subscribe()
        assert sub_id
        assert q is not None

    def test_publish_delivers_to_subscriber(self):
        b = SSEBroadcaster()
        sub_id, q = b.subscribe()
        b.publish('test', {'msg': 'hello'})
        event, data = q.get(timeout=1)
        assert event == 'test'
        assert data['msg'] == 'hello'

    def test_unsubscribe_removes_subscriber(self):
        b = SSEBroadcaster()
        sub_id, q = b.subscribe()
        b.unsubscribe(sub_id)
        b.publish('test', {'msg': 'hello'})
        import queue

        with pytest.raises(queue.Empty):
            q.get(timeout=0.5)

    def test_multiple_subscribers_all_receive(self):
        b = SSEBroadcaster()
        _, q1 = b.subscribe()
        _, q2 = b.subscribe()
        b.publish('e', {'n': 1})
        assert q1.get(timeout=1) == ('e', {'n': 1})
        assert q2.get(timeout=1) == ('e', {'n': 1})

    def test_on_local_listener(self):
        b = SSEBroadcaster()
        handler = MagicMock()
        b.on('job_status', handler)
        b.publish('job_status', {'id': '1'})
        handler.assert_called_once_with({'id': '1'})

    def test_off_removes_listener(self):
        b = SSEBroadcaster()
        handler = MagicMock()
        b.on('job_status', handler)
        b.off('job_status', handler)
        b.publish('job_status', {'id': '1'})
        handler.assert_not_called()

    def test_listener_exception_does_not_crash(self):
        b = SSEBroadcaster()

        def broken(data):
            raise RuntimeError('boom')

        b.on('e', broken)
        # 不应抛出异常
        b.publish('e', {'ok': 1})

    def test_stale_subscriber_removed_after_full_queue(self):
        b = SSEBroadcaster(maxsize=2)
        sub_id, q = b.subscribe()
        # 填满队列并持续 publish 触发淘汰
        for i in range(6):
            b.publish('e', {'i': i})
        # 订阅者应被移除
        assert sub_id not in b._subscribers

    def test_publish_targeted_event_type(self):
        b = SSEBroadcaster()
        handler = MagicMock()
        b.on('type_a', handler)
        b.publish('type_b', {'x': 1})
        handler.assert_not_called()


class TestInitApp:
    def test_init_app_sets_state(self):
        app = MagicMock()
        app.state = MagicMock()
        b = init_app(app, maxsize=50)
        assert app.state.sse is b
