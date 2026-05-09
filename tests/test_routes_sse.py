"""SSE 端点集成测试 — FastAPI 路由层

SSE 事件流不通过 HTTP 测试（生成器阻塞 q.get 无法被 GeneratorExit 中断），
改为直接测试 SSEBroadcaster + FastAPI 应用状态集成。
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# =============================================================================
# /api/stats — JSON 统计端点
# =============================================================================


class TestStatsEndpoint:
    """GET /api/stats 返回 JSON 统计"""

    @pytest.fixture(autouse=True)
    def _setup_repo(self, app_instance):
        mock_repo = MagicMock()
        mock_repo.get_stats.return_value = {
            'queued': 2,
            'printing': 1,
            'today_completed': 10,
            'today_failed': 1,
            'success_rate': 90.9,
            'total': 100,
        }
        app_instance.state.job_repo = mock_repo

    def test_stats_returns_200(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/stats')
        assert resp.status_code == 200

    def test_stats_is_json(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/stats')
        assert 'application/json' in resp.headers['content-type']

    def test_stats_contains_values(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/stats')
        data = resp.json()
        assert data['queued'] == 2
        assert data['today_completed'] == 10

    def test_stats_zero_values(self, app_instance):
        app_instance.state.job_repo.get_stats.return_value = {
            'queued': 0,
            'printing': 0,
            'today_completed': 0,
            'today_failed': 0,
            'success_rate': 0.0,
            'total': 0,
        }
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/stats')
        assert resp.status_code == 200

    def test_stats_without_job_repo_returns_500(self, app_instance):
        del app_instance.state.job_repo
        from fastapi.testclient import TestClient

        client = TestClient(app_instance, raise_server_exceptions=False)
        resp = client.get('/api/stats')
        assert resp.status_code == 500


# =============================================================================
# /api/events 端点注册验证
# =============================================================================


class TestSSEEndpointRegistration:
    """/api/events 端点在应用中正确注册"""

    def test_endpoint_registered(self, app_instance):
        routes = [r.path for r in app_instance.routes]
        assert '/api/events' in routes

    def test_endpoint_accepts_get(self, app_instance):
        methods = set()
        for route in app_instance.routes:
            if hasattr(route, 'path') and route.path == '/api/events':
                methods = route.methods
                break
        assert 'GET' in methods

    def test_sse_broadcaster_available(self, app_instance):
        """app.state.sse 可在端点中访问"""
        assert hasattr(app_instance.state, 'sse')
        from app.services.sse_broadcaster import SSEBroadcaster

        assert isinstance(app_instance.state.sse, SSEBroadcaster)

    def test_sse_subscribe_publish_cycle(self, app_instance):
        """通过 app.state.sse 的完整发布/订阅周期"""
        import json

        broadcaster = app_instance.state.sse
        sub_id, q = broadcaster.subscribe()

        # 模拟端点行为：发布一个事件
        test_data = {'job_id': '1', 'status': 'completed'}
        broadcaster.publish('job_status', test_data)

        # 模拟端点行为：从 queue 读取并格式化 SSE
        event_type, data = q.get(timeout=1)
        sse = f'event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'

        assert sse.startswith('event: job_status')
        assert '"status": "completed"' in sse
        assert sse.endswith('\n\n')

    def test_sse_subscriber_cleanup(self, app_instance):
        """模拟端点 finally 块中的 unsubscribe"""
        broadcaster = app_instance.state.sse
        sub_id, q = broadcaster.subscribe()

        sub_count_before = len(broadcaster._subscribers)
        broadcaster.unsubscribe(sub_id)
        sub_count_after = len(broadcaster._subscribers)

        assert sub_count_before == 1
        assert sub_count_after == 0


# =============================================================================
# /api/logs — REST 日志接口
# =============================================================================


class TestLogsEndpoint:
    """GET /api/logs — uses temp dir to avoid Windows file locking"""

    @pytest.fixture(autouse=True)
    def _setup_temp_log(self, tmp_path, monkeypatch):
        """Per-test: isolate log file in temp directory."""
        log_dir = tmp_path / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        self._tmp_log = log_dir / 'print_server.log'
        monkeypatch.setattr('app._paths.persistent_dir', lambda: tmp_path)
        monkeypatch.setattr('app.routes.api.persistent_dir', lambda: tmp_path)

    def _ensure_log(self, lines):
        with open(self._tmp_log, 'w', encoding='utf-8') as f:
            f.writelines(lines)

    def _remove_log(self):
        if self._tmp_log.exists():
            self._tmp_log.unlink(missing_ok=True)

    def test_logs_with_lines_param(self, app_instance):
        self._ensure_log(['line1\n', 'line2\n', 'line3\n'])
        try:
            from fastapi.testclient import TestClient

            client = TestClient(app_instance)
            resp = client.get('/api/logs?lines=2')
            assert resp.status_code == 200
            data = resp.json()
            assert len(data['lines']) == 2
        finally:
            self._remove_log()

    def test_logs_all_lines(self, app_instance):
        self._ensure_log(['line1\n', 'line2\n', 'line3\n'])
        try:
            from fastapi.testclient import TestClient

            client = TestClient(app_instance)
            resp = client.get('/api/logs')
            assert resp.status_code == 200
            data = resp.json()
            assert len(data['lines']) == 3
        finally:
            self._remove_log()

    def test_logs_file_not_found(self, app_instance):
        self._remove_log()
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs')
        assert resp.status_code == 200
        assert resp.json() == {'lines': []}
