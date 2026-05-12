"""API 路由集成测试 — /api/health"""

from unittest.mock import MagicMock

import pytest


class TestHealthEndpoint:
    """GET /api/health — 参数化测试"""

    @pytest.fixture(autouse=True)
    def _setup_queue(self, app_instance):
        """给 app.state 注入 mock job_queue"""
        app_instance.state.job_queue = MagicMock()
        app_instance.state.job_queue.queue_size.return_value = 3

    @pytest.mark.parametrize(
        'queue_val,expected_qsize',
        [
            (3, 3),
            (5, 5),
            (0, 0),
        ],
    )
    def test_health(self, app_instance, queue_val, expected_qsize):
        from fastapi.testclient import TestClient

        app_instance.state.job_queue.queue_size.return_value = queue_val
        resp = TestClient(app_instance).get('/api/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert isinstance(data['version'], str)
        assert data['queue_size'] == expected_qsize
