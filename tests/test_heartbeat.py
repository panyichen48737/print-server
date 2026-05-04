"""测试心跳检测"""
import time
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.services.heartbeat import HeartbeatMonitor


class TestHeartbeatMonitor:
    def test_start_creates_daemon_thread(self):
        hb = HeartbeatMonitor(interval=0.1)
        hb.start()
        assert hb._thread is not None
        assert hb._thread.is_alive()
        assert hb._thread.daemon is True
        hb.stop()

    def test_double_start_is_idempotent(self):
        hb = HeartbeatMonitor(interval=0.1)
        hb.start()
        thread = hb._thread
        hb.start()  # 再次 start 不应创建新线程
        assert hb._thread is thread
        hb.stop()

    def test_cleanup_fn_is_called(self):
        cleanup = MagicMock()
        hb = HeartbeatMonitor(interval=0.05, cleanup_fn=cleanup)
        hb.start()
        time.sleep(0.12)
        hb.stop()
        assert cleanup.called

    def test_recover_fn_is_called(self):
        recover = MagicMock()
        hb = HeartbeatMonitor(interval=0.05, recover_stuck_fn=recover)
        hb.start()
        time.sleep(0.12)
        hb.stop()
        assert recover.called

    def test_stop_does_not_raise(self):
        hb = HeartbeatMonitor()
        hb.stop()  # 未启动就 stop

    def test_run_with_timeout_handles_slow_fn(self):
        hb = HeartbeatMonitor(interval=1)
        def slow():
            time.sleep(5)
        hb._run_with_timeout(slow, 'slow', timeout=0.1)  # 不应阻塞太久

    def test_run_with_timeout_handles_exception(self):
        hb = HeartbeatMonitor(interval=1)
        def broken():
            raise ValueError('test')
        hb._run_with_timeout(broken, 'broken')  # 不应抛出

    def test_loop_stops_on_stop_event(self):
        hb = HeartbeatMonitor(interval=0.01)
        hb.start()
        hb.stop()
        assert hb._stop_evt.is_set()
