"""测试 PrintEngine 文件类型分发与任务管理逻辑"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.printing.engine import PrintEngine


class TestPrintEngine:
    """PrintEngine 文件分发、清理和取消测试"""

    def setup_method(self):
        self.config = MagicMock()
        self.excel_lock = threading.Lock()
        self.ppt_lock = threading.Lock()

    # ── 路由测试 ──────────────────────────────────────────────

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_pdf_routes_to_pdf_backend(self, MockPdfBackend, MockOfficeBackend, MockImageBackend):
        """.pdf 文件调用 PdfBackend.print_file"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_pdf = MockPdfBackend.return_value

        engine.print_file('test.pdf', '.pdf', 'job-pdf', None)

        mock_pdf.print_file.assert_called_once_with(
            'test.pdf', 'job-pdf', {'_file_type': '.pdf'}, lock=None
        )

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_office_routes_to_office_then_pdf(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """.docx 文件先调 OfficeBackend.convert_to_pdf，再调 PdfBackend.print_file，
        并传入 word_lock"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_office = MockOfficeBackend.return_value
        mock_pdf = MockPdfBackend.return_value
        temp_pdf = r'C:\temp\conv_test.pdf'
        mock_office.convert_to_pdf.return_value = temp_pdf
        word_lock = threading.Lock()

        engine.print_file('test.docx', '.docx', 'job-docx', word_lock)

        mock_office.convert_to_pdf.assert_called_once_with(
            'test.docx', {'_file_type': '.docx', '_word_lock': word_lock}
        )
        mock_pdf.print_file.assert_called_once_with(
            temp_pdf, 'job-docx', {'_file_type': '.docx', '_word_lock': word_lock}
        )

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_image_routes_to_image_backend(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """.jpg 文件调用 ImageBackend.print_file"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_image = MockImageBackend.return_value

        engine.print_file('test.jpg', '.jpg', 'job-img', None)

        mock_image.print_file.assert_called_once_with(
            'test.jpg', 'job-img', {'_file_type': '.jpg'}, lock=None
        )

    # ── 扩展名全覆盖 ──────────────────────────────────────────

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_all_office_extensions_use_office_backend(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """所有 Office 扩展名都应走 convert_to_pdf 路径"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_office = MockOfficeBackend.return_value
        mock_office.convert_to_pdf.return_value = r'C:\temp\out.pdf'

        office_exts = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
        for i, ext in enumerate(office_exts):
            engine.print_file(f'test{ext}', ext, f'job-off-{i}', None)

        assert mock_office.convert_to_pdf.call_count == len(office_exts)

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_all_image_extensions_use_image_backend(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """所有图片扩展名都应路由到 ImageBackend"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_image = MockImageBackend.return_value

        img_exts = [
            '.jpg',
            '.jpeg',
            '.png',
            '.bmp',
            '.gif',
            '.webp',
            '.tiff',
            '.tif',
            '.heic',
            '.heif',
        ]
        for i, ext in enumerate(img_exts):
            engine.print_file(f'test{ext}', ext, f'job-img-{i}', None)

        assert mock_image.print_file.call_count == len(img_exts)

    # ── 异常测试 ──────────────────────────────────────────────

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_unsupported_type_raises_value_error(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """不支持的文件类型应抛出 ValueError"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)

        with pytest.raises(ValueError, match='不支持的文件类型'):
            engine.print_file('test.xyz', '.xyz', 'job-xyz', None)

    # ── 取消任务 ──────────────────────────────────────────────

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_cancel_active_job_routes_to_backend(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """取消活跃任务应调用对应 backend.cancel"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_pdf = MockPdfBackend.return_value
        mock_pdf.cancel.return_value = True

        # 直接注入活跃任务（print_file 同步返回后会自行清理）
        engine._active_jobs['job-cancel'] = {'backend': mock_pdf}
        result = engine.cancel_active_job('job-cancel')

        assert result is True
        mock_pdf.cancel.assert_called_once_with('job-cancel', {})

    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_cancel_nonexistent_job_returns_false(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend
    ):
        """取消不存在的任务应返回 False"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)

        result = engine.cancel_active_job('nonexistent')

        assert result is False

    # ── Office 临时文件清理 ───────────────────────────────────

    @patch('app.printing.engine.safe_remove')
    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_office_cleanup_temp_pdf_in_finally(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend, mock_safe_remove
    ):
        """Office 转换后 finally 块应调用 safe_remove 删除临时 PDF"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_office = MockOfficeBackend.return_value
        temp_pdf = r'C:\temp\cleanup_me.pdf'
        mock_office.convert_to_pdf.return_value = temp_pdf

        engine.print_file('test.docx', '.docx', 'job-cleanup', threading.Lock())

        mock_safe_remove.assert_called_once_with(temp_pdf)

    @patch('app.printing.engine.safe_remove')
    @patch('app.printing.engine.ImageBackend')
    @patch('app.printing.engine.OfficeBackend')
    @patch('app.printing.engine.PdfBackend')
    def test_office_cleanup_on_pdf_print_failure(
        self, MockPdfBackend, MockOfficeBackend, MockImageBackend, mock_safe_remove
    ):
        """Office 转换后即便 PdfBackend.print_file 抛异常，也应清理临时 PDF"""
        engine = PrintEngine(self.config, self.excel_lock, self.ppt_lock)
        mock_office = MockOfficeBackend.return_value
        mock_pdf = MockPdfBackend.return_value
        temp_pdf = r'C:\temp\fail_cleanup.pdf'
        mock_office.convert_to_pdf.return_value = temp_pdf
        mock_pdf.print_file.side_effect = RuntimeError('打印失败')

        with pytest.raises(RuntimeError):
            engine.print_file('test.docx', '.docx', 'job-fail', threading.Lock())

        mock_safe_remove.assert_called_once_with(temp_pdf)
