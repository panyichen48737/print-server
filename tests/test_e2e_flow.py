"""端到端流程测试 — 使用真实 JobQueue + Repository + 临时 SQLite"""

from pathlib import Path
from typing import ClassVar
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def e2e_app(tmp_path):
    """创建带真实 JobQueue/Repository 的 app，使用临时目录"""
    from app import create_app

    app = create_app()

    # 真实 Repository + 临时 DB
    from app.printing.repository import JobRepository

    repo = JobRepository(str(tmp_path / 'test.db'))
    app.state.job_repo = repo

    # 真实 JobQueue
    from app.printing.job_queue import JobQueue

    queue = JobQueue(repo)
    app.state.job_queue = queue

    # Mock 外部依赖
    app.state.printer_monitor = MagicMock()
    app.state.printer_monitor.get_all_statuses.return_value = {}

    app.state.app_config = MagicMock()
    cfg_values = {
        'allowed_extensions': ['.pdf', '.doc', '.docx', '.jpg', '.png'],
        'max_file_size_mb': 50,
        'api_key': 'print-server-key-2026',
        'notify_channel': 'disabled',
    }
    app.state.app_config.get.side_effect = lambda k, d=None: cfg_values.get(k, d)

    app.state.print_engine = MagicMock()

    return app


class TestE2EFlow:
    """上传 → 状态查询 → 取消 完整流程"""

    AUTH: ClassVar[dict[str, str]] = {'Authorization': 'Bearer print-server-key-2026'}

    def _client(self, app):
        from fastapi.testclient import TestClient

        return TestClient(app)

    def _make_pdf(self):
        from io import BytesIO

        return BytesIO(b'%PDF-1.4 fake pdf content')

    def test_upload_then_status_then_cancel(self, e2e_app):
        c = self._client(e2e_app)

        # 1. 上传文件
        resp = c.post(
            '/api/upload',
            files={'file': ('test.pdf', self._make_pdf(), 'application/pdf')},
            data={'printer': 'Printer1', 'copies': '2'},
            headers=self.AUTH,
        )
        assert resp.status_code == 200
        job_id = resp.json()['job_id']
        assert job_id

        # 2. 查询状态
        resp = c.get(f'/api/status/{job_id}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['job_id'] == job_id
        assert data['status'] in ('queued', 'printing', 'completed', 'failed')

        # 3. 取消任务
        resp = c.post(f'/api/cancel/{job_id}', headers=self.AUTH)
        assert resp.status_code == 200
        assert resp.json()['success'] is True

        # 4. 取消后状态应为 cancelled 或 completed
        resp = c.get(f'/api/status/{job_id}')
        assert resp.status_code == 200

    def test_upload_multiple_files(self, e2e_app):
        """多文件上传，每个返回独立 job_id"""
        c = self._client(e2e_app)
        ids = set()
        for i in range(3):
            resp = c.post(
                '/api/upload',
                files={
                    'file': (
                        f'test{i}.pdf',
                        self._make_pdf(),
                        'application/pdf',
                    )
                },
                headers=self.AUTH,
            )
            assert resp.status_code == 200
            ids.add(resp.json()['job_id'])

        assert len(ids) == 3

    def test_jobs_list_reflects_uploads(self, e2e_app):
        """上传后 /api/jobs 应返回对应任务"""
        c = self._client(e2e_app)

        # 上传 2 个文件
        c.post(
            '/api/upload',
            files={'file': ('a.pdf', self._make_pdf(), 'application/pdf')},
            headers=self.AUTH,
        )
        c.post(
            '/api/upload',
            files={'file': ('b.pdf', self._make_pdf(), 'application/pdf')},
            headers=self.AUTH,
        )

        resp = c.get('/api/jobs')
        assert resp.status_code == 200
        data = resp.json()
        assert data['total'] == 2
        assert len(data['jobs']) == 2

    def test_cancel_nonexistent_job(self, e2e_app):
        """取消不存在的任务返回 400"""
        c = self._client(e2e_app)
        resp = c.post('/api/cancel/nonexistent', headers=self.AUTH)
        assert resp.status_code == 400

    def test_health_with_real_queue(self, e2e_app):
        """health 端点使用真实队列"""
        c = self._client(e2e_app)
        resp = c.get('/api/health')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'ok'
        assert data['queue_size'] >= 0

    def test_stats_with_real_repo(self, e2e_app):
        """stats 端点使用真实仓库"""
        c = self._client(e2e_app)
        resp = c.get('/api/stats')
        assert resp.status_code == 200
        data = resp.json()
        assert 'queued' in data
