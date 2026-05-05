"""测试 SSEBroadcaster.cleanup_idle_subscribers — 空闲订阅者清理"""

import time

from app.services.sse_broadcaster import SSEBroadcaster


class TestCleanupIdleSubscribers:
    """空闲订阅者清理"""

    def test_idle_subscriber_removed(self):
        """订阅后不活动超过 timeout 的订阅者应被移除"""
        b = SSEBroadcaster()
        sub_id, _ = b.subscribe()
        time.sleep(0.05)
        removed = b.cleanup_idle_subscribers(timeout=0.01)
        assert removed == 1
        assert sub_id not in b._subscribers

    def test_active_subscriber_not_removed(self):
        """有读取事件的订阅者不应被移除——这里用长 timeout 确保不超时"""
        b = SSEBroadcaster()
        sub_id, q = b.subscribe()
        b.publish('e', {'n': 1})
        q.get(timeout=1)  # 消费事件，模拟活跃
        removed = b.cleanup_idle_subscribers(timeout=100)
        assert removed == 0
        assert sub_id in b._subscribers

    def test_cleanup_returns_count(self):
        """返回被移除的订阅者数量"""
        b = SSEBroadcaster()
        b.subscribe()
        b.subscribe()
        time.sleep(0.05)
        removed = b.cleanup_idle_subscribers(timeout=0.01)
        assert removed == 2

    def test_no_idle_subscribers(self):
        """没有订阅者时返回 0"""
        b = SSEBroadcaster()
        removed = b.cleanup_idle_subscribers(timeout=0.01)
        assert removed == 0

    def test_recent_subscriber_not_removed(self):
        """刚订阅的订阅者不应被清理"""
        b = SSEBroadcaster()
        sub_id, _ = b.subscribe()
        # 立即清理，timeout 远大于已过时间
        removed = b.cleanup_idle_subscribers(timeout=100)
        assert removed == 0
        assert sub_id in b._subscribers

    def test_mixed_idle_and_active(self):
        """混合场景：只清理空闲的，保留活跃的"""
        b = SSEBroadcaster()
        idle_id, _ = b.subscribe()
        time.sleep(0.05)
        active_id, q = b.subscribe()
        b.publish('e', {'n': 1})
        q.get(timeout=1)

        removed = b.cleanup_idle_subscribers(timeout=0.01)
        assert removed == 1
        assert idle_id not in b._subscribers
        assert active_id in b._subscribers

    def test_cleanup_removes_subscribe_time(self):
        """清理后应同时移除 _subscribe_time 记录"""
        b = SSEBroadcaster()
        sub_id, _ = b.subscribe()
        time.sleep(0.05)
        b.cleanup_idle_subscribers(timeout=0.01)
        assert sub_id not in b._subscribe_time

    def test_cleanup_with_default_timeout(self):
        """默认 timeout=300 秒，刚订阅的不被移除"""
        b = SSEBroadcaster()
        sub_id, _ = b.subscribe()
        removed = b.cleanup_idle_subscribers()  # 默认 300s
        assert removed == 0
        assert sub_id in b._subscribers

    def test_unsubscribe_cleans_subscribe_time(self):
        """unsubscribe 应同时清理 _subscribe_time"""
        b = SSEBroadcaster()
        sub_id, _ = b.subscribe()
        assert sub_id in b._subscribe_time
        b.unsubscribe(sub_id)
        assert sub_id not in b._subscribe_time
