"""JobExecutor 和 JobWorker 测试

依赖 mock：printer_engine, repo, event_bus, config
"""

import threading
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_job(tmp_path):
    pdf_path = tmp_path / 'test.pdf'
    pdf_path.write_text('fake pdf content')
    return {
        'id': 'job-001',
        'filename': 'test.pdf',
        'filepath': str(pdf_path),
        'file_type': '.pdf',
        'status': 'queued',
        'source': 'api',
        'printer_name': 'HP LaserJet',
        'copies': 1,
        'duplex': False,
        'color': True,
        'paper_size': 'A4',
    }


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {
        'job_timeout': 300,
        'auto_retry_count': 0,
    }.get(key, default)
    return cfg


@pytest.fixture
def job_executor(mock_config):
    from app.printing.worker import JobExecutor

    repo = MagicMock()
    engine = MagicMock()
    bus = MagicMock()
    word_lock = threading.Lock()
    cancelled = set()

    def get_cancelled(job_id):
        return job_id in cancelled

    executor = JobExecutor(mock_config, bus, repo, engine, get_cancelled, word_lock)
    executor._cancelled = cancelled
    return executor


# =============================================================================
# JobExecutor.execute
# =============================================================================


class TestJobExecutorExecute:
    """JobExecutor.execute 的主要路径"""

    def test_normal_completion(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._print_engine.print_file.return_value = True

        success, error = job_executor.execute('job-001', 1)

        assert success is True
        assert error is None
        job_executor._repo.update_status.assert_any_call('job-001', 'printing', None)
        job_executor._repo.update_status.assert_any_call('job-001', 'completed', None)

    def test_engine_returns_false(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._print_engine.print_file.return_value = False

        success, error = job_executor.execute('job-001', 1)

        assert success is False

    def test_job_not_found(self, job_executor):
        job_executor._repo.get_job.return_value = None

        success, error = job_executor.execute('job-999', 1)

        assert success is True  # 不存在的任务视为完成（跳过）
        assert error is None

    def test_cancelled_before_execution(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._cancelled.add('job-001')

        success, error = job_executor.execute('job-001', 1)

        assert success is True
        job_executor._print_engine.print_file.assert_not_called()

    def test_print_exception(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._print_engine.print_file.side_effect = RuntimeError('打印机离线')

        success, error = job_executor.execute('job-001', 1)

        assert success is False
        assert '打印机离线' in error

    def test_make_temp_copy_called(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._print_engine.print_file.return_value = True

        with patch('app.core.utils.tempfile.NamedTemporaryFile') as tmp_mock:
            tmp_file = MagicMock()
            tmp_file.name = r'C:\tmp\__temp__.pdf'
            tmp_mock.return_value.__enter__.return_value = tmp_file
            with patch('app.core.utils.shutil.copy2') as copy_mock:
                job_executor.execute('job-001', 1)

                copy_mock.assert_called_once_with(mock_job['filepath'], tmp_file.name)

    def test_cancel_during_printing(self, job_executor, mock_job):
        """打印中取消应返回 cancelled"""
        job_executor._repo.get_job.return_value = mock_job

        # 让打印引擎耗时，然后超时
        def slow_print(*args, **kwargs):
            import time

            time.sleep(10)
            return True

        job_executor._print_engine.print_file.side_effect = slow_print
        job_executor._cancelled.add('job-001')

        # 执行，使用短超时
        job_executor.config.get.side_effect = lambda key, default=None: {
            'job_timeout': 0.1,
            'auto_retry_count': 0,
        }.get(key, default)

        result = job_executor.execute('job-001', 1)
        assert result == (True, None)  # cancelled -> (True, None)


# =============================================================================
# JobWorker
# =============================================================================


class TestJobWorker:
    """JobWorker 初始化和脱离 pythoncom 的逻辑"""

    @pytest.fixture
    def worker(self, mock_config):
        from app.printing.worker import JobWorker

        queue = MagicMock()
        repo = MagicMock()
        bus = MagicMock()
        engine = MagicMock()
        evt = threading.Event()

        worker = JobWorker(1, mock_config, queue, repo, bus, evt, engine, threading.Lock())
        return worker, evt, queue

    def test_worker_initialized(self, worker):
        w, _, _ = worker
        assert w.worker_id == 1
        assert w._executor is not None

    def test_process_calls_executor(self, worker):
        w, evt, q = worker
        from app.printing.worker import RetryHandler

        w._repo.get_job.return_value = {
            'id': 'job-001',
            'status': 'queued',
            'filename': 'test.pdf',
            'filepath': '/tmp/test.pdf',
            'source': 'api',
        }
        w._job_queue.is_cancelled.return_value = False

        with patch.object(w, '_executor') as mock_exec:
            mock_exec.execute.return_value = (True, None)
            handler = RetryHandler(w._config, w._repo, mock_exec)
            handler.run_with_retry('job-001', 1)
            mock_exec.execute.assert_called_once_with('job-001', 1, 0)

    def test_process_cancelled_job(self, worker):
        w, evt, q = worker
        from app.printing.worker import RetryHandler

        q.is_cancelled.return_value = True
        w._repo.get_job.return_value = {
            'id': 'job-001',
            'status': 'cancelled',
            'filepath': '/tmp/test.pdf',
        }

        with patch.object(w, '_executor') as mock_exec:
            mock_exec.execute.return_value = (True, None)
            handler = RetryHandler(w._config, w._repo, mock_exec)
            handler.run_with_retry('job-001', 1)
            mock_exec.execute.assert_called_once()

    def test_process_missing_job(self, worker):
        w, evt, q = worker
        from app.printing.worker import RetryHandler

        w._repo.get_job.return_value = None

        handler = RetryHandler(w._config, w._repo, w._executor)
        handler.run_with_retry('job-001', 1)

    def test_process_retry_on_failure(self, worker, mock_config):
        w, evt, q = worker
        from app.printing.worker import RetryHandler

        w._repo.get_job.return_value = {
            'id': 'job-001',
            'status': 'queued',
            'filename': 'test.pdf',
            'filepath': '/tmp/test.pdf',
            'source': 'api',
        }
        w._job_queue.is_cancelled.return_value = False
        # 配置 2 次重试
        w._config.get.side_effect = lambda key, default=None: {
            'auto_retry_count': 2,
        }.get(key, default)

        with patch.object(w, '_executor') as mock_exec:
            mock_exec.execute.return_value = (False, '打印失败')
            handler = RetryHandler(w._config, w._repo, mock_exec)
            handler.run_with_retry('job-001', 1)

            # 应重试 3 次（1 次初始 + 2 次重试）
            assert mock_exec.execute.call_count == 3
            assert w._repo.increment_retry.call_count == 2


# =============================================================================
# JobExecutor._update_and_broadcast
# =============================================================================


class TestUpdateAndBroadcast:
    """_update_and_broadcast 状态更新 + 事件发送"""

    def test_publishes_job_status(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._print_engine.print_file.return_value = True
        job_executor.execute('job-001', 1)

        # 验证 event_bus.publish 至少被调用两次（printing + completed）
        assert job_executor._event_bus.publish.call_count >= 2
        call_args = job_executor._event_bus.publish.call_args_list[0]
        assert call_args[0][0] == 'job_status'

    def test_failed_event_contains_error(self, job_executor, mock_job):
        job_executor._repo.get_job.return_value = mock_job
        job_executor._print_engine.print_file.side_effect = RuntimeError('卡纸')

        job_executor.execute('job-001', 1)

        # 最后一次 publish 应包含 error 字段
        calls = job_executor._event_bus.publish.call_args_list
        failed_call = None
        for c in calls:
            data = c[0][1]
            if data.get('status') == 'failed':
                failed_call = data
        assert failed_call is not None
        assert failed_call['error'] is not None
        assert '卡纸' in failed_call['error']
