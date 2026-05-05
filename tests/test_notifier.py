"""测试通知工具函数"""

from app.services.notifier import format_error_message, is_print_related_error


class TestFormatErrorMessage:
    def test_empty_error_returns_empty(self):
        assert format_error_message('') == ''
        assert format_error_message(None) == ''

    def test_known_error_pattern(self):
        assert 'Chrome' in format_error_message('未找到 Chromium')
        assert 'Chrome' in format_error_message('Chromium 启动失败')

    def test_timeout_error(self):
        assert '超时' in format_error_message('打印超时')
        assert '超时' in format_error_message('connection timeout')

    def test_printer_not_found(self):
        result = format_error_message('打印机 "HP101" 未找到')
        assert '打印机' in result or '找不到' in result

    def test_word_failure(self):
        assert 'Word' in format_error_message('Word.Application 调用失败')

    def test_unknown_error_truncated(self):
        long_msg = 'x' * 300
        result = format_error_message(long_msg)
        assert len(result) < len(long_msg)
        assert '未知错误' in result

    def test_all_known_patterns_match(self):
        """每个 KNOWN_ERROR_PATTERNS 至少匹配对应示例"""
        samples = [
            '未找到 Chromium 浏览器',
            '打印超时: 300秒',
            '用户取消',
            '打印机 HP1020 未找到',
            'Word.Application 调用失败',
            'Excel.Application 出错',
            'PowerPoint.Application 异常',
            '不支持的文件类型',
            '文件过大',
            '磁盘空间不足',
            '权限不足',
            'Quark API 调用失败',
            'nssm install 失败',
        ]
        for sample in samples:
            assert format_error_message(sample) != '', f'{sample} 应匹配已知模式'


class TestIsPrintRelatedError:
    def test_empty_returns_true(self):
        assert is_print_related_error('') is True
        assert is_print_related_error(None) is True

    def test_system_errors_return_false(self):
        assert is_print_related_error('磁盘空间不足') is False
        assert is_print_related_error('权限不足') is False
        assert is_print_related_error('文件过大') is False

    def test_print_errors_return_true(self):
        assert is_print_related_error('打印机离线') is True
        assert is_print_related_error('Chromium 未找到') is True
        assert is_print_related_error('Word 调用失败') is True
