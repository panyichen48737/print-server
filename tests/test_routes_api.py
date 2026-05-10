"""API 路由集成测试 — /api/health 和 /api/logs"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


class TestHealthEndpoint:
    """GET /api/health"""

    @pytest.fixture(autouse=True)
    def _setup_queue(self, app_instance):
        """给 app.state 注入 mock job_queue"""
        app_instance.state.job_queue = MagicMock()
        app_instance.state.job_queue.queue_size.return_value = 3

    # ------------------------------------------------------------------
    # 200 响应
    # ------------------------------------------------------------------

    def test_health_returns_200(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/health')
        assert resp.status_code == 200

    # ------------------------------------------------------------------
    # 响应结构
    # ------------------------------------------------------------------

    def test_health_contains_expected_keys(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/health')
        data = resp.json()
        assert 'status' in data
        assert 'version' in data
        assert 'queue_size' in data

    # ------------------------------------------------------------------
    # status 值
    # ------------------------------------------------------------------

    def test_health_status_is_ok(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        data = client.get('/api/health').json()
        assert data['status'] == 'ok'

    # ------------------------------------------------------------------
    # version 类型
    # ------------------------------------------------------------------

    def test_health_version_is_string(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        data = client.get('/api/health').json()
        assert isinstance(data['version'], str)

    def test_health_version_nonempty(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        data = client.get('/api/health').json()
        assert len(data['version']) > 0

    # ------------------------------------------------------------------
    # queue_size
    # ------------------------------------------------------------------

    def test_health_queue_size_matches_mock(self, app_instance):
        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        data = client.get('/api/health').json()
        assert data['queue_size'] == 3

    def test_health_queue_size_updates(self, app_instance):
        """修改 mock 返回值后应反映到端点响应中"""
        app_instance.state.job_queue.queue_size.return_value = 5

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        data = client.get('/api/health').json()
        assert data['queue_size'] == 5

    def test_health_queue_size_zero(self, app_instance):
        app_instance.state.job_queue.queue_size.return_value = 0

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        data = client.get('/api/health').json()
        assert data['queue_size'] == 0


class TestLogsEndpoint:
    """GET /api/logs"""

    @pytest.fixture
    def temp_log_dir(self):
        """创建临时目录模拟 persistent_dir"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'logs'), exist_ok=True)
            yield tmpdir

    # ------------------------------------------------------------------
    # lines 参数
    # ------------------------------------------------------------------

    @patch('app.routes.system.persistent_dir')
    def test_logs_returns_requested_lines(self, mock_persistent_dir, app_instance, temp_log_dir):
        mock_persistent_dir.return_value = temp_log_dir
        lines = [f'line{i}\n' for i in range(1, 6)]
        log_file = os.path.join(temp_log_dir, 'logs', 'print_server.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs?lines=3')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['lines']) == 3

    # ------------------------------------------------------------------
    # 默认 lines=50
    # ------------------------------------------------------------------

    @patch('app.routes.system.persistent_dir')
    def test_logs_default_returns_all_when_less_than_50(
        self, mock_persistent_dir, app_instance, temp_log_dir
    ):
        """文件行数 < 默认 50 时，应返回全部行"""
        mock_persistent_dir.return_value = temp_log_dir
        lines = ['line1\n', 'line2\n', 'line3\n']
        log_file = os.path.join(temp_log_dir, 'logs', 'print_server.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['lines']) == 3

    # ------------------------------------------------------------------
    # 文件名中文字符 (UTF-8 编码保证)
    # ------------------------------------------------------------------

    @patch('app.routes.system.persistent_dir')
    def test_logs_chinese_content(self, mock_persistent_dir, app_instance, temp_log_dir):
        mock_persistent_dir.return_value = temp_log_dir
        lines = ['打印成功\n', '任务完成\n']
        log_file = os.path.join(temp_log_dir, 'logs', 'print_server.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs?lines=10')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['lines']) == 2
        assert data['lines'][0] == '打印成功\n'
        assert data['lines'][1] == '任务完成\n'

    # ------------------------------------------------------------------
    # 文件不存在
    # ------------------------------------------------------------------

    @patch('app.routes.system.persistent_dir')
    def test_logs_file_not_found_returns_empty_list(
        self, mock_persistent_dir, app_instance, temp_log_dir
    ):
        mock_persistent_dir.return_value = temp_log_dir

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs')
        assert resp.status_code == 200
        assert resp.json() == {'lines': []}

    # ------------------------------------------------------------------
    # 大文件 — lines 参数小于文件行数
    # ------------------------------------------------------------------

    @patch('app.routes.system.persistent_dir')
    def test_logs_large_file_truncates(self, mock_persistent_dir, app_instance, temp_log_dir):
        """文件 100 行，请求 5 行，应返回末尾 5 行"""
        mock_persistent_dir.return_value = temp_log_dir
        lines = [f'line{i}\n' for i in range(100)]
        log_file = os.path.join(temp_log_dir, 'logs', 'print_server.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs?lines=5')
        assert resp.status_code == 200
        data = resp.json()
        assert len(data['lines']) == 5
        # 应返回最后 5 行
        assert data['lines'] == ['line95\n', 'line96\n', 'line97\n', 'line98\n', 'line99\n']

    # ------------------------------------------------------------------
    # lines=0 的边界行为
    # ------------------------------------------------------------------

    @patch('app.routes.system.persistent_dir')
    def test_logs_zero_lines_returns_empty(self, mock_persistent_dir, app_instance, temp_log_dir):
        mock_persistent_dir.return_value = temp_log_dir
        lines = ['line1\n', 'line2\n']
        log_file = os.path.join(temp_log_dir, 'logs', 'print_server.log')
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        from fastapi.testclient import TestClient

        client = TestClient(app_instance)
        resp = client.get('/api/logs?lines=0')
        assert resp.status_code == 200
        data = resp.json()
        assert data['lines'] == []
