"""SSE 事件路由集成测试

验证事件从发布者到 SSE 订阅者的完整链路，覆盖本次 SSEBroadcaster 替换改动的核心逻辑。
"""

import queue
from unittest.mock import MagicMock

import pytest

from app.services.log_broadcaster import LogBroadcaster
from app.services.sse_broadcaster import SSEBroadcaster

# =============================================================================
# SSEBroadcaster 路由：publish → subscriber + EventBus
# =============================================================================


class TestSSEPublishToSubscriber:
    """SSEBroadcaster.publish → subscriber queue 送达"""

    def test_subscriber_receives_event(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        sse_broadcaster.publish('test_event', {'msg': 'hello'})
        ev_type, data = q.get(timeout=1)
        assert ev_type == 'test_event'
        assert data == {'msg': 'hello'}

    def test_multiple_subscribers_all_receive(self, sse_broadcaster):
        subs = [sse_broadcaster.subscribe() for _ in range(3)]
        sse_broadcaster.publish('multi', {'n': 42})
        for _, q in subs:
            ev_type, data = q.get(timeout=1)
            assert ev_type == 'multi'
            assert data == {'n': 42}

    def test_event_types_isolated(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        sse_broadcaster.publish('type_a', {'a': 1})
        sse_broadcaster.publish('type_b', {'b': 2})
        t1, _ = q.get(timeout=1)
        t2, _ = q.get(timeout=1)
        assert {t1, t2} == {'type_a', 'type_b'}

    def test_unsubscribed_receives_no_events(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        sse_broadcaster.unsubscribe(sub_id)
        sse_broadcaster.publish('ghost', {})
        with pytest.raises(queue.Empty):
            q.get(timeout=0.5)


class TestSSEPublishToEventBus:
    """SSEBroadcaster.publish → EventBus 本地监听器送达"""

    def test_local_listener_receives(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('job_status', handler)
        sse_broadcaster.publish('job_status', {'id': '1'})
        handler.assert_called_once_with({'id': '1'})

    def test_off_removes_listener(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('job_status', handler)
        sse_broadcaster.off('job_status', handler)
        sse_broadcaster.publish('job_status', {'id': '1'})
        handler.assert_not_called()

    def test_listener_exception_does_not_crash(self, sse_broadcaster):
        def broken(data):
            raise ValueError('oops')

        handler2 = MagicMock()
        sse_broadcaster.on('test', broken)
        sse_broadcaster.on('test', handler2)
        sse_broadcaster.publish('test', {})
        handler2.assert_called_once()

    def test_different_event_type_does_not_trigger(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('type_a', handler)
        sse_broadcaster.publish('type_b', {})
        handler.assert_not_called()


class TestSSEDualDelivery:
    """同一次 publish → subscriber + EventBus 两端都送达"""

    def test_dual_delivery(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('job_status', handler)
        sub_id, q = sse_broadcaster.subscribe()

        sse_broadcaster.publish('job_status', {'id': '42'})

        # subscriber 收到
        ev_type, data = q.get(timeout=1)
        assert ev_type == 'job_status'
        assert data == {'id': '42'}

        # EventBus listener 收到
        handler.assert_called_once_with({'id': '42'})

    def test_dual_delivery_multiple_events(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('log', handler)
        sub_id, q = sse_broadcaster.subscribe()

        for i in range(5):
            sse_broadcaster.publish('log', {'n': i})

        for i in range(5):
            _, data = q.get(timeout=1)
            assert data == {'n': i}

        assert handler.call_count == 5


# =============================================================================
# 模拟 Worker._update_and_broadcast → SSE subscriber
# =============================================================================


class TestJobStatusEventRouting:
    """模拟 JobQueue / Worker 发布 job_status 事件"""

    def test_job_status_via_broadcaster(self, sse_broadcaster):
        """Worker._update_and_broadcast 使用 SSEBroadcaster 时，SSE 订阅者收到事件"""
        sub_id, q = sse_broadcaster.subscribe()

        # Worker._update_and_broadcast 调用的等价逻辑
        data = {
            'job_id': 'job-001',
            'filename': 'test.pdf',
            'status': 'printing',
            'source': 'web',
            'ts': '2026-05-05T00:00:00',
        }
        sse_broadcaster.publish('job_status', data)

        ev_type, received = q.get(timeout=1)
        assert ev_type == 'job_status'
        assert received['job_id'] == 'job-001'
        assert received['status'] == 'printing'
        assert received['filename'] == 'test.pdf'

    def test_job_status_with_error(self, sse_broadcaster):
        """失败状态包含 error 字段"""
        sub_id, q = sse_broadcaster.subscribe()
        data = {
            'job_id': 'job-002',
            'filename': 'broken.doc',
            'status': 'failed',
            'source': 'api',
            'error': '打印机离线',
        }
        sse_broadcaster.publish('job_status', data)

        _, received = q.get(timeout=1)
        assert received['status'] == 'failed'
        assert received['error'] == '打印机离线'

    def test_job_status_multiple_subscribers(self, sse_broadcaster):
        """多个 SSE 订阅者各自收到 job_status"""
        subs = [sse_broadcaster.subscribe() for _ in range(3)]
        sse_broadcaster.publish('job_status', {'job_id': 'm', 'status': 'completed'})
        for _, q in subs:
            _, d = q.get(timeout=1)
            assert d['status'] == 'completed'


# =============================================================================
# 模拟 PrinterMonitor._poll → SSE subscriber
# =============================================================================


class TestPrinterStatusEventRouting:
    """PrinterMonitor 使用 SSEBroadcaster 时的事件路由"""

    def test_printer_status_via_broadcaster(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()

        # PrinterMonitor._poll 中的等价发布逻辑
        pr_data = {
            'name': 'HP LaserJet',
            'overall': 'ready',
            'statuses': [],
        }
        sse_broadcaster.publish('printer_status', pr_data)

        ev_type, received = q.get(timeout=1)
        assert ev_type == 'printer_status'
        assert received['name'] == 'HP LaserJet'
        assert received['overall'] == 'ready'

    def test_printer_removed_event(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        sse_broadcaster.publish(
            'printer_status',
            {
                'name': 'Old Printer',
                'overall': 'removed',
                'statuses': [],
            },
        )
        _, received = q.get(timeout=1)
        assert received['overall'] == 'removed'

    def test_printer_status_with_active_statuses(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        sse_broadcaster.publish(
            'printer_status',
            {
                'name': 'Busy Printer',
                'overall': 'busy',
                'statuses': [{'key': 'printing', 'label': '打印中'}],
            },
        )
        _, received = q.get(timeout=1)
        assert received['overall'] == 'busy'
        assert received['statuses'][0]['key'] == 'printing'

    def test_printer_status_publishes_to_eventbus_too(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('printer_status', handler)
        sse_broadcaster.publish('printer_status', {'name': 'P1', 'overall': 'ready'})
        handler.assert_called_once()


# =============================================================================
# LogBroadcaster + SSEBroadcaster 集成
# =============================================================================


class TestLogBroadcasterIntegration:
    """LogBroadcaster(SSEBroadcaster) → SSE subscriber"""

    def test_log_reaches_subscriber(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        lb = LogBroadcaster(broadcaster=sse_broadcaster)
        lb.write('INFO 这是一条测试日志')

        ev_type, data = q.get(timeout=1)
        assert ev_type == 'log'
        assert '测试日志' in data['message']
        assert data['level'] == 'INFO'

    def test_multiple_logs_queued(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        lb = LogBroadcaster(broadcaster=sse_broadcaster)
        for i in range(5):
            lb.write(f'INFO 日志第{i}条')

        for i in range(5):
            _, data = q.get(timeout=1)
            assert f'日志第{i}条' in data['message']

    def test_empty_log_skipped(self, sse_broadcaster):
        sub_id, q = sse_broadcaster.subscribe()
        lb = LogBroadcaster(broadcaster=sse_broadcaster)
        lb.write('')
        lb.write('   ')

        with pytest.raises(queue.Empty):
            q.get(timeout=0.5)

    def test_no_broadcaster_does_not_crash(self):
        lb = LogBroadcaster(broadcaster=None)
        lb.write('INFO 没有 broadcaster 不应崩溃')
        lb.write('')
        # 通过 —— 没有异常

    def test_log_publishes_to_eventbus_too(self, sse_broadcaster):
        handler = MagicMock()
        sse_broadcaster.on('log', handler)
        lb = LogBroadcaster(broadcaster=sse_broadcaster)
        lb.write('INFO test')
        handler.assert_called_once()


# =============================================================================
# 队列满处理
# =============================================================================


class TestFullQueueHandling:
    """订阅者队列满时：丢弃旧事件，EventBus 仍送达"""

    def test_full_queue_drops_oldest(self):
        """maxsize=2, publish 3 次 → 最新事件仍在, 旧事件被丢弃"""
        b = SSEBroadcaster(maxsize=2)
        sub_id, q = b.subscribe()
        b.publish('log', {'n': 1})
        b.publish('log', {'n': 2})
        b.publish('log', {'n': 3})  # 队列满 → 丢弃 n=1

        received = []
        while True:
            try:
                _, d = q.get(timeout=0.3)
                received.append(d['n'])
            except queue.Empty:
                break
        assert 1 not in received  # 最旧的被丢弃
        assert 3 in received

    def test_full_queue_eventbus_still_delivers(self):
        b = SSEBroadcaster(maxsize=1)
        handler = MagicMock()
        b.on('test', handler)
        b.subscribe()  # 有 subscriber 占队列
        b.publish('test', {'n': 1})
        b.publish('test', {'n': 2})  # 队列满
        assert handler.call_count == 2

    def test_stale_subscriber_removed_after_limit(self):
        b = SSEBroadcaster(maxsize=1)
        sub_id, q = b.subscribe()
        # 连续 3 次队列满（subscriber 不消费）
        for i in range(4):
            b.publish('ev', {'n': i})
        # subscriber 应已被移除
        assert sub_id not in b._subscribers


# =============================================================================
# init_app 集成测试
# =============================================================================


class TestInitApp:
    """init_app 正确初始化 app.state"""

    def test_init_app_sets_state(self, app_instance):
        assert hasattr(app_instance.state, 'event_bus')
        assert hasattr(app_instance.state, 'sse')
        from app.services.sse_broadcaster import SSEBroadcaster

        assert isinstance(app_instance.state.sse, SSEBroadcaster)

    def test_sse_endpoint_registered(self, app_instance):
        routes = [r.path for r in app_instance.routes]
        assert '/api/events' in routes

    def test_subscribe_publish_cycle_via_app(self, app_instance):
        """通过 app.state.sse 的完整 publish/subscribe 周期"""
        broadcaster = app_instance.state.sse
        sub_id, q = broadcaster.subscribe()
        broadcaster.publish('job_status', {'id': '42'})
        ev_type, data = q.get(timeout=1)
        assert ev_type == 'job_status'
        assert data == {'id': '42'}
