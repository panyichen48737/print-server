"""测试 WorkerPool"""
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.printing.worker_pool import WorkerPool


class TestWorkerPool:
    @pytest.fixture
    def config(self):
        cfg = MagicMock()
        cfg.get.return_value = 2
        return cfg

    @pytest.fixture
    def pool(self, config):
        return WorkerPool(config, event_bus=MagicMock())

    def test_start_creates_workers(self, pool):
        pool._word_lock = threading.Lock()
        pool.start(MagicMock(), MagicMock(), MagicMock())
        assert len(pool._workers) == 2
        for w in pool._workers:
            assert w._thread.is_alive()
        pool.stop()

    def test_stop_no_workers(self, pool):
        pool.stop()  # 不应抛出

    def test_double_stop_safe(self, pool):
        pool._word_lock = threading.Lock()
        pool.start(MagicMock(), MagicMock(), MagicMock())
        pool.stop()
        pool.stop()  # 再次 stop 不应抛出

    def test_start_without_word_lock(self, config):
        pool = WorkerPool(config, event_bus=MagicMock())
        pool.start(MagicMock(), MagicMock(), MagicMock())
        assert len(pool._workers) == 2
        pool.stop()
