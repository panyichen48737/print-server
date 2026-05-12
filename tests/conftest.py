"""共享 fixtures — pytest 全局"""

from unittest.mock import MagicMock

import pytest

# 默认 API Key（与 app.core.auth 默认值一致）
_DEFAULT_API_KEY = 'print-server-key-2026'


@pytest.fixture
def sse_broadcaster():
    """创建 SSEBroadcaster 实例用于集成测试"""
    from app.services.sse_broadcaster import SSEBroadcaster

    return SSEBroadcaster()


@pytest.fixture
def mock_config():
    """通用配置 mock"""
    cfg = MagicMock()

    def fake_get(key, default=None):
        values = {
            'port': 5000,
            'log_level': 'INFO',
            'max_file_size_mb': 50,
            'allowed_extensions': ['.pdf', '.doc', '.docx', '.jpg', '.png'],
            'api_key': _DEFAULT_API_KEY,
        }
        return values.get(key, default)

    cfg.get.side_effect = fake_get
    return cfg


@pytest.fixture
def mock_repo():
    """MagicMock JobRepository"""
    repo = MagicMock()
    repo.add_job.return_value = 'test-job-id'
    repo.get_job.return_value = {
        'id': 'test-job-id',
        'status': 'queued',
        'filename': 'test.pdf',
    }
    repo.get_jobs.return_value = []
    repo.count_jobs.return_value = 0
    repo.get_stats.return_value = {
        'queued': 0,
        'printing': 0,
        'today_completed': 0,
        'today_failed': 0,
        'success_rate': 0.0,
        'total': 0,
    }
    repo.get_daily_counts.return_value = []
    return repo


@pytest.fixture
def mock_queue():
    """MagicMock JobQueue"""
    q = MagicMock()
    q.queue_size.return_value = 0
    q.add_job.return_value = 'test-job-id'
    q.cancel_job.return_value = (True, None)
    q.cancel_all_queued.return_value = 0
    q.retry_job.return_value = ('new-job-id', None)
    return q


@pytest.fixture
def mock_printer_monitor():
    """MagicMock PrinterMonitor"""
    m = MagicMock()
    m.get_all_statuses.return_value = {'Printer1': {'status': 'idle'}}
    return m


@pytest.fixture
def auth_header():
    """有效的 Authorization header"""
    return {'Authorization': f'Bearer {_DEFAULT_API_KEY}'}


@pytest.fixture
def app_instance():
    """FastAPI 应用实例（无 lifespan，测试专用）

    app.state 已预置 mock 对象，可直接用于路由测试。
    """
    from app import create_app

    app = create_app()
    app.state.job_queue = MagicMock()
    app.state.job_queue.queue_size.return_value = 0
    app.state.job_queue.add_job.return_value = 'test-job-id'
    app.state.job_queue.cancel_job.return_value = (True, None)
    app.state.job_queue.cancel_all_queued.return_value = 0
    app.state.job_queue.retry_job.return_value = ('new-job-id', None)

    app.state.job_repo = MagicMock()
    app.state.job_repo.get_job.return_value = {
        'id': 'test-job-id',
        'status': 'queued',
        'filename': 'test.pdf',
    }
    app.state.job_repo.get_jobs.return_value = []
    app.state.job_repo.count_jobs.return_value = 0
    app.state.job_repo.get_stats.return_value = {
        'queued': 0,
        'printing': 0,
        'today_completed': 0,
        'today_failed': 0,
        'success_rate': 0.0,
        'total': 0,
    }
    app.state.job_repo.get_daily_counts.return_value = []

    app.state.printer_monitor = MagicMock()
    app.state.printer_monitor.get_all_statuses.return_value = {'Printer1': {'status': 'idle'}}

    app.state.app_config = MagicMock()
    cfg_values = {
        'port': 5000,
        'log_level': 'INFO',
        'max_file_size_mb': 50,
        'allowed_extensions': ['.pdf', '.doc', '.docx', '.jpg', '.png'],
        'api_key': _DEFAULT_API_KEY,
        'notify_channel': 'disabled',
    }
    app.state.app_config.get.side_effect = lambda k, d=None: cfg_values.get(k, d)

    app.state.print_engine = MagicMock()
    return app
