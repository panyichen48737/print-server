"""测试 JobQueue"""

from unittest.mock import MagicMock, patch

import pytest

from app.printing.job_queue import JobQueue


@pytest.fixture
def repo():
    r = MagicMock()
    r.add_job.return_value = 'test-job-id'
    return r


@pytest.fixture
def event_bus():
    return MagicMock()


@pytest.fixture
def config():
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {
        'worker_count': 2,
    }.get(key, default)
    return cfg


@pytest.fixture
def queue(repo, event_bus):
    return JobQueue(repo, event_bus=event_bus)


class TestJobQueue:
    def test_add_job_returns_id(self, queue, repo):
        job_id = queue.add_job('test.pdf', '/p/test.pdf')
        assert job_id == 'test-job-id'
        repo.add_job.assert_called_once()

    def test_add_job_pushes_to_queue(self, queue):
        queue.add_job('f.pdf', '/p/f.pdf')
        assert queue.queue_size() == 1

    def test_get_for_processing_returns_job(self, queue):
        queue.add_job('f.pdf', '/p/f.pdf')
        job_id = queue.get_for_processing(timeout=0.5)
        assert job_id == 'test-job-id'

    def test_get_for_processing_empty(self, queue):
        assert queue.get_for_processing(timeout=0.1) is None

    def test_cancel_job_nonexistent(self, queue, repo):
        repo.get_job.return_value = None
        success, error = queue.cancel_job('bad-id')
        assert success is False
        assert '不存在' in error

    def test_cancel_queued_job(self, queue, repo, event_bus):
        repo.get_job.return_value = {
            'id': 'job-1',
            'filename': 'f.pdf',
            'filepath': '/p/f.pdf',
            'status': 'queued',
            'source': 'web',
        }
        success, error = queue.cancel_job('job-1')
        assert success is True
        repo.update_status.assert_called_with('job-1', 'failed', '用户取消')
        event_bus.publish.assert_called()

    def test_cancel_completed_job_fails(self, queue, repo):
        repo.get_job.return_value = {'id': '1', 'status': 'completed'}
        success, error = queue.cancel_job('1')
        assert success is False

    def test_is_cancelled(self, queue):
        queue.mark_cancelled('job-1')
        assert queue.is_cancelled('job-1') is True
        assert queue.is_cancelled('job-2') is False

    def test_clear_cancelled(self, queue):
        queue.mark_cancelled('job-1')
        queue.clear_cancelled('job-1')
        assert queue.is_cancelled('job-1') is False

    def test_cancel_all_queued(self, queue, repo):
        repo.get_jobs_by_status.return_value = [
            {'id': '1', 'filename': 'a.pdf', 'filepath': '/a.pdf', 'source': 'web'},
            {'id': '2', 'filename': 'b.pdf', 'filepath': '/b.pdf', 'source': 'web'},
        ]
        count = queue.cancel_all_queued()
        assert count == 2
        repo.batch_update_status.assert_called()

    def test_cancel_all_queued_no_jobs(self, queue, repo):
        repo.get_jobs_by_status.return_value = []
        assert queue.cancel_all_queued() == 0

    def test_retry_job_nonexistent(self, queue, repo):
        repo.get_job.return_value = None
        new_id, error = queue.retry_job('bad')
        assert new_id is None
        assert error is not None

    def test_retry_job_not_failed(self, queue, repo):
        repo.get_job.return_value = {'id': '1', 'status': 'completed'}
        new_id, error = queue.retry_job('1')
        assert new_id is None

    def test_retry_success(self, queue, repo):
        repo.get_job.return_value = {
            'id': '1',
            'status': 'failed',
            'filename': 'f.pdf',
            'filepath': '/f.pdf',
            'file_size': 100,
            'file_type': '.pdf',
        }
        new_id, error = queue.retry_job('1')
        assert new_id == 'test-job-id'

    def test_recover_stuck_jobs(self, queue, repo):
        from datetime import datetime, timedelta

        old = (datetime.now() - timedelta(hours=1)).isoformat()
        repo.get_jobs_by_status.return_value = [
            {'id': 'stuck-1', 'created_at': old},
            {'id': 'stuck-2', 'created_at': old},
        ]
        queue.recover_stuck_jobs()
        assert repo.update_status.call_count >= 1

    def test_queue_size(self, queue):
        assert queue.queue_size() == 0
        queue.add_job('a.pdf', '/a.pdf')
        assert queue.queue_size() == 1


# =============================================================================
# Worker lifecycle tests (replaces test_worker_pool.py)
# =============================================================================


class TestWorkerLifecycle:
    """JobQueue 内联 Worker 生命周期"""

    @pytest.fixture
    def q(self, repo, event_bus, config):
        """JobQueue with config for worker lifecycle tests"""
        return JobQueue(repo, event_bus=event_bus, config=config)

    def test_start_creates_workers(self, q, repo, event_bus):
        with patch.dict('sys.modules', {'pythoncom': MagicMock()}):
            q.start(count=2)
            assert q.running_workers() == 2
            q.stop()

    def test_stop_all_workers(self, q, repo, event_bus):
        with patch.dict('sys.modules', {'pythoncom': MagicMock()}):
            q.start(count=2)
            q.stop()
            assert q.running_workers() == 0

    def test_double_stop_safe(self, q, repo, event_bus):
        with patch.dict('sys.modules', {'pythoncom': MagicMock()}):
            q.start(count=2)
            q.stop()
            q.stop()  # 不应抛出

    def test_stop_no_workers(self, q):
        q.stop()  # 不应抛出

    def test_start_without_print_engine(self, q, repo, event_bus):
        """set_print_engine 未调用时 start 仍可运行（打印会失败）"""
        with patch.dict('sys.modules', {'pythoncom': MagicMock()}):
            q.start(count=1)
            assert q.running_workers() == 1
            q.stop()
