"""共享 fixtures — pytest 全局"""
from unittest.mock import MagicMock

import pytest


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
        }
        return values.get(key, default)

    cfg.get.side_effect = fake_get
    return cfg


@pytest.fixture
def mock_repo():
    """MagicMock JobRepository"""
    repo = MagicMock()
    repo.add_job.return_value = 'test-job-id'
    return repo


@pytest.fixture
def app_instance():
    """FastAPI 应用实例（无 lifespan，测试专用）"""
    from app import create_app
    app = create_app()
    return app
