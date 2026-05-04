"""测试路径工具"""
import sys
from unittest.mock import patch

import pytest

from app._paths import app_root, data_root, ensure_dir


class TestAppRoot:
    @patch('app._paths.sys.frozen', False, create=True)
    def test_dev_mode(self):
        root = app_root()
        assert root.endswith('print_server')

    @patch('app._paths.sys.frozen', True, create=True)
    @patch('app._paths.sys.executable', '/fake/path/server.exe')
    def test_frozen_mode(self):
        root = app_root()
        assert root == '/fake/path'


class TestDataRoot:
    @patch('app._paths.sys.frozen', False, create=True)
    def test_dev_mode_equals_app_root(self):
        assert data_root() == app_root()

    @patch('app._paths.sys.frozen', True, create=True)
    @patch('app._paths.sys._MEIPASS', '/fake/meipass', create=True)
    def test_frozen_mode_returns_meipass(self):
        assert data_root() == '/fake/meipass'


class TestEnsureDir:
    def test_creates_dir(self, tmp_path):
        target = tmp_path / 'a' / 'b' / 'c'
        result = ensure_dir(str(target))
        assert target.exists()
        assert target.is_dir()
        assert result == str(target)

    def test_existing_dir_does_not_raise(self, tmp_path):
        target = tmp_path / 'existing'
        target.mkdir(parents=True)
        ensure_dir(str(target))  # 不应抛出

    def test_returns_full_path(self, tmp_path):
        result = ensure_dir(str(tmp_path), 'x', 'y')
        assert result == str(tmp_path / 'x' / 'y')
