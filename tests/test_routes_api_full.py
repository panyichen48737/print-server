"""API 路由全覆盖测试 — auth + 全部端点 + 边界情况"""

from typing import ClassVar
from unittest.mock import MagicMock

import pytest


def _client(app, **kwargs):
    from fastapi.testclient import TestClient

    return TestClient(app, **kwargs)


class TestAuth:
    """require_auth 依赖保护"""

    ENDPOINTS: ClassVar[list[tuple[str, str]]] = [
        ('POST', '/api/print'),
        ('POST', '/api/cancel/test-job-id'),
        ('POST', '/api/upload'),
        ('POST', '/api/set_default_printer'),
        ('POST', '/api/retry/test-job-id'),
        ('POST', '/api/test_notification'),
        ('POST', '/api/cancel_all_queued'),
    ]

    @pytest.mark.parametrize('method,path', ENDPOINTS)
    def test_no_token_returns_401(self, app_instance, method, path):
        c = _client(app_instance)
        resp = c.request(method, path)
        assert resp.status_code == 401

    @pytest.mark.parametrize('method,path', ENDPOINTS)
    def test_wrong_token_returns_401(self, app_instance, method, path):
        c = _client(app_instance)
        resp = c.request(method, path, headers={'Authorization': 'Bearer wrong-key'})
        assert resp.status_code == 401

    # 无需 auth 的端点
    PUBLIC_ENDPOINTS: ClassVar[list[tuple[str, str]]] = [
        ('GET', '/api/health'),
        ('GET', '/api/version'),
        ('GET', '/api/status/test-job-id'),
        ('GET', '/api/printers'),
        ('GET', '/api/printers/status'),
        ('GET', '/api/jobs'),
        ('GET', '/api/stats'),
        ('GET', '/api/logs'),
    ]

    @pytest.mark.parametrize('method,path', PUBLIC_ENDPOINTS)
    def test_public_endpoints_no_auth(self, app_instance, method, path):
        """公开端点不返回 401"""
        c = _client(app_instance)
        resp = c.request(method, path)
        assert resp.status_code != 401


class TestVersion:
    def test_version_returns_fields(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/version')
        assert resp.status_code == 200
        data = resp.json()
        assert 'version' in data
        assert 'python_version' in data
        assert 'build_date' in data


class TestStatus:
    def test_status_found(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/status/test-job-id')
        assert resp.status_code == 200
        data = resp.json()
        assert data['job_id'] == 'test-job-id'
        assert data['status'] == 'queued'

    def test_status_not_found(self, app_instance):
        app_instance.state.job_repo.get_job.return_value = None
        c = _client(app_instance)
        resp = c.get('/api/status/nonexistent')
        assert resp.status_code == 404
        assert '不存在' in resp.json()['detail']

    def test_status_failed_with_error(self, app_instance):
        app_instance.state.job_repo.get_job.return_value = {
            'id': 'failed-job',
            'status': 'failed',
            'filename': 'bad.pdf',
            'error_message': '打印失败',
        }
        c = _client(app_instance)
        resp = c.get('/api/status/failed-job')
        assert resp.status_code == 200
        data = resp.json()
        assert data['status'] == 'failed'
        assert data['error'] == '打印失败'


class TestJobs:
    def test_jobs_default_params(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/jobs')
        assert resp.status_code == 200
        data = resp.json()
        assert 'jobs' in data
        assert 'total' in data

    def test_jobs_with_limit_and_offset(self, app_instance):
        app_instance.state.job_repo.get_jobs.return_value = [{'id': '1'}, {'id': '2'}]
        app_instance.state.job_repo.count_jobs.return_value = 2
        c = _client(app_instance)
        resp = c.get('/api/jobs?limit=10&offset=0')
        assert resp.status_code == 200
        assert len(resp.json()['jobs']) == 2

    def test_jobs_with_status_filter(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/jobs?status=queued')
        assert resp.status_code == 200
        app_instance.state.job_repo.get_jobs.assert_called_with(
            status='queued', search=None, limit=20, offset=0
        )

    def test_jobs_with_search(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/jobs?search=test')
        assert resp.status_code == 200
        app_instance.state.job_repo.get_jobs.assert_called_with(
            status=None, search='test', limit=20, offset=0
        )


class TestPrinters:
    def test_list_printers(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/printers')
        assert resp.status_code == 200
        data = resp.json()
        assert 'printers' in data
        assert 'Printer1' in data['printers']

    def test_printer_status(self, app_instance):
        c = _client(app_instance)
        resp = c.get('/api/printers/status')
        assert resp.status_code == 200
        data = resp.json()
        assert 'printers' in data
        assert data['printers']['Printer1']['status'] == 'idle'

    def test_printers_no_monitor_returns_500(self, app_instance):
        del app_instance.state.printer_monitor
        c = _client(app_instance, raise_server_exceptions=False)
        resp = c.get('/api/printers')
        assert resp.status_code == 500

    def test_printer_status_no_monitor_returns_500(self, app_instance):
        del app_instance.state.printer_monitor
        c = _client(app_instance, raise_server_exceptions=False)
        resp = c.get('/api/printers/status')
        assert resp.status_code == 500


class TestCancel:
    def test_cancel_success(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post('/api/cancel/test-job-id', headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_cancel_failure(self, app_instance, auth_header):
        app_instance.state.job_queue.cancel_job.return_value = (False, '任务不存在')
        c = _client(app_instance)
        resp = c.post('/api/cancel/bad-id', headers=auth_header)
        assert resp.status_code == 400

    def test_cancel_print_server_error(self, app_instance, auth_header):
        from app.core.exceptions import PrintServerError

        app_instance.state.job_queue.cancel_job.side_effect = PrintServerError('server error')
        c = _client(app_instance)
        resp = c.post('/api/cancel/test-job-id', headers=auth_header)
        assert resp.status_code == 500


class TestSetDefaultPrinter:
    def test_set_success(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post(
            '/api/set_default_printer',
            json={'printer': 'Printer2'},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_set_empty_body_returns_500(self, app_instance, auth_header):
        """空 body 导致 Pydantic ValidationError（在路由内部），返回 500"""
        c = _client(app_instance, raise_server_exceptions=False)
        resp = c.post('/api/set_default_printer', json={}, headers=auth_header)
        assert resp.status_code == 500


class TestRetry:
    def test_retry_success(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post('/api/retry/failed-job', headers=auth_header)
        assert resp.status_code == 200
        data = resp.json()
        assert data['success'] is True
        assert data['new_job_id'] == 'new-job-id'

    def test_retry_failure(self, app_instance, auth_header):
        app_instance.state.job_queue.retry_job.return_value = (None, '重试失败')
        c = _client(app_instance)
        resp = c.post('/api/retry/failed-job', headers=auth_header)
        assert resp.status_code == 400
        assert '重试失败' in resp.json()['detail']


class TestCancelAll:
    def test_cancel_all_success(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post('/api/cancel_all_queued', headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['cancelled'] == 0

    def test_cancel_all_with_count(self, app_instance, auth_header):
        app_instance.state.job_queue.cancel_all_queued.return_value = 5
        c = _client(app_instance)
        resp = c.post('/api/cancel_all_queued', headers=auth_header)
        assert resp.json()['cancelled'] == 5


class TestNotification:
    def test_notification_disabled(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post('/api/test_notification', headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['channel'] == 'disabled'

    def test_notification_dingtalk(self, app_instance, auth_header):
        app_instance.state.app_config.get.side_effect = lambda k, d=None: {
            'notify_channel': 'dingtalk',
        }.get(k, d)
        app_instance.state.dingtalk = MagicMock()
        c = _client(app_instance)
        resp = c.post('/api/test_notification', headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['channel'] == 'dingtalk'

    def test_notification_bark(self, app_instance, auth_header):
        app_instance.state.app_config.get.side_effect = lambda k, d=None: {
            'notify_channel': 'bark',
        }.get(k, d)
        app_instance.state.bark = MagicMock()
        c = _client(app_instance)
        resp = c.post('/api/test_notification', headers=auth_header)
        assert resp.status_code == 200
        assert resp.json()['channel'] == 'bark'


class TestPrint:
    def _make_file(self):
        from io import BytesIO

        return BytesIO(b'%PDF-1.4 fake pdf content')

    def test_print_success(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post(
            '/api/print',
            files={'file': ('test.pdf', self._make_file(), 'application/pdf')},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_print_unsupported_type(self, app_instance, auth_header):
        app_instance.state.app_config.get.side_effect = lambda k, d=None: {
            'allowed_extensions': ['.pdf'],
            'max_file_size_mb': 50,
            'api_key': 'print-server-key-2026',
        }.get(k, d)
        c = _client(app_instance)
        resp = c.post(
            '/api/print',
            files={'file': ('bad.exe', b'fake content', 'application/octet-stream')},
            headers=auth_header,
        )
        assert resp.status_code == 400

    def test_print_with_params(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post(
            '/api/print',
            files={'file': ('test.pdf', self._make_file(), 'application/pdf')},
            data={'printer': 'Printer1', 'copies': '2', 'color': '1'},
            headers=auth_header,
        )
        assert resp.status_code == 200

    def test_print_empty_filename_returns_422(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post(
            '/api/print',
            files={'file': ('', b'', 'application/pdf')},
            headers=auth_header,
        )
        assert resp.status_code == 422

    def test_print_no_file_returns_422(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post('/api/print', headers=auth_header)
        assert resp.status_code == 422


class TestUpload:
    def _make_file(self):
        from io import BytesIO

        return BytesIO(b'%PDF-1.4 fake pdf content')

    def test_upload_success(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post(
            '/api/upload',
            files={'file': ('test.pdf', self._make_file(), 'application/pdf')},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()['success'] is True

    def test_upload_success_with_params(self, app_instance, auth_header):
        c = _client(app_instance)
        resp = c.post(
            '/api/upload',
            files={'file': ('test.pdf', self._make_file(), 'application/pdf')},
            data={'printer': 'Printer1', 'copies': '3', 'duplex': '1'},
            headers=auth_header,
        )
        assert resp.status_code == 200
        assert resp.json()['success'] is True
