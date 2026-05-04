"""测试通用工具函数"""
import os
import time
from datetime import datetime
from unittest.mock import patch

import pytest

from app.utils import safe_int, format_time, safe_remove


class TestSafeInt:
    def test_valid_int(self):
        assert safe_int('42', 0) == 42
        assert safe_int('-1', 0) == -1

    def test_invalid_returns_default(self):
        assert safe_int('abc', 10) == 10
        assert safe_int('', 0) == 0
        assert safe_int(None, 5) == 5

    def test_zero_is_valid(self):
        assert safe_int('0', 100) == 0


class TestFormatTime:
    def test_no_arg_returns_string(self):
        t = format_time()
        assert isinstance(t, str)
        assert len(t) == 19  # YYYY-MM-DD HH:MM:SS

    def test_with_datetime(self):
        dt = datetime(2025, 1, 2, 3, 4, 5)
        assert format_time(dt) == '2025-01-02 03:04:05'

    def test_iso_format(self):
        dt = datetime(2024, 12, 31, 23, 59, 59)
        assert format_time(dt) == '2024-12-31 23:59:59'


class TestSafeRemove:
    def test_removes_existing_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        assert os.path.exists(path)
        safe_remove(path)
        assert not os.path.exists(path)

    def test_none_path_ignored(self):
        safe_remove(None)

    def test_file_not_found_ignored(self):
        safe_remove('/nonexistent/path/file.txt')

    def test_empty_path_ignored(self):
        safe_remove('')

    def test_removes_with_label_success(self):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        safe_remove(path, label='测试文件')
        assert not os.path.exists(path)
