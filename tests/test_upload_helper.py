"""测试文件上传辅助模块"""

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# 确保项目根在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.upload import UploadResult, handle_file_upload


class TestHandleFileUpload:
    """测试 handle_file_upload"""

    @pytest.fixture
    def config(self):
        """模拟 Config 对象"""
        cfg = MagicMock()

        def fake_get(key, default=None):
            values = {
                'allowed_extensions': ['.pdf', '.doc', '.docx', '.jpg', '.png'],
                'max_file_size_mb': 50,
            }
            return values.get(key, default)

        cfg.get.side_effect = fake_get
        return cfg

    @pytest.fixture
    def queue_mgr(self):
        """模拟 JobQueue 对象"""
        qm = MagicMock()
        qm.add_job.return_value = 'test-job-id-123'
        return qm

    def test_empty_filename(self, config, queue_mgr):
        """空文件名应返回失败"""
        result = handle_file_upload('', b'content', config, queue_mgr)
        assert isinstance(result, UploadResult)
        assert result.success is False
        assert '文件名' in result.error

    def test_unsupported_extension(self, config, queue_mgr):
        """不支持的文件类型应返回失败"""
        result = handle_file_upload('test.exe', b'content', config, queue_mgr)
        assert result.success is False
        assert '不支持' in result.error

    def test_file_too_large(self, config, queue_mgr):
        """超过大小限制的文件应返回失败"""
        large_content = b'x' * (51 * 1024 * 1024)  # 51MB
        result = handle_file_upload('test.pdf', large_content, config, queue_mgr)
        assert result.success is False
        assert '文件过大' in result.error

    def test_successful_upload(self, config, queue_mgr):
        """有效文件应成功入队"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('app.services.upload.ensure_dir', return_value=tmpdir):
                result = handle_file_upload('test.pdf', b'pdf content', config, queue_mgr)
                assert result.success is True
                assert result.job_id == 'test-job-id-123'
                # 验证 add_job 被调用
                queue_mgr.add_job.assert_called_once()
                args, kwargs = queue_mgr.add_job.call_args
                assert args[0] == 'test.pdf'  # filename

    def test_upload_with_print_params(self, config, queue_mgr):
        """应传递打印参数到 queue_mgr.add_job"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('app.services.upload.ensure_dir', return_value=tmpdir):
                result = handle_file_upload(
                    'doc.docx',
                    b'doc content',
                    config,
                    queue_mgr,
                    source='web',
                    printer='HP123',
                    copies='2',
                    duplex='1',
                    color='0',
                    paper_size='A3',
                )
                assert result.success is True
                _, kwargs = queue_mgr.add_job.call_args
                assert kwargs['source'] == 'web'
                assert kwargs['printer_name'] == 'HP123'
                assert kwargs['copies'] == 2


class TestUploadResult:
    """测试 UploadResult dataclass"""

    def test_success_result(self):
        result = UploadResult(success=True, job_id='job-1')
        assert result.success is True
        assert result.job_id == 'job-1'
        assert result.error == ''

    def test_failure_result(self):
        result = UploadResult(success=False, error='something wrong')
        assert result.success is False
        assert result.error == 'something wrong'
        assert result.job_id == ''
