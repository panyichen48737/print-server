"""测试路径工具"""

from pathlib import Path
from unittest.mock import patch

from app.core._paths import app_root, config_dir, data_root, ensure_dir, log_dir, persistent_dir


class TestAppRoot:
    @patch('app.core._paths.sys.frozen', False, create=True)
    def test_dev_mode(self):
        root = app_root()
        assert 'print_server' in str(root) or 'print-server' in str(root)

    @patch('app.core._paths.sys.frozen', True, create=True)
    @patch('app.core._paths.sys.executable', '/fake/path/server.exe')
    def test_frozen_mode(self):
        root = app_root()
        assert root == Path('/fake/path')


class TestDataRoot:
    @patch('app.core._paths.sys.frozen', False, create=True)
    def test_dev_mode_equals_app_root(self):
        assert data_root() == app_root()

    @patch('app.core._paths.sys.frozen', True, create=True)
    @patch('app.core._paths.sys.executable', '/fake/path/server.exe')
    def test_frozen_mode_returns_app_root(self):
        assert data_root() == Path('/fake/path')


class TestEnsureDir:
    def test_creates_dir(self, tmp_path):
        target = tmp_path / 'a' / 'b' / 'c'
        result = ensure_dir(str(target))
        assert target.exists()
        assert target.is_dir()
        assert result == target

    def test_existing_dir_does_not_raise(self, tmp_path):
        target = tmp_path / 'existing'
        target.mkdir(parents=True)
        ensure_dir(str(target))  # 不应抛出

    def test_returns_full_path(self, tmp_path):
        result = ensure_dir(str(tmp_path), 'x', 'y')
        assert result == tmp_path / 'x' / 'y'


class TestConfigDir:
    @patch('app.core._paths.os.environ', {'APPDATA': r'C:\Users\test\AppData\Roaming'})
    def test_dev_mode_uses_appdata(self):
        assert config_dir() == Path(r'C:\Users\test\AppData\Roaming\iOSPrintServer')

    @patch('app.core._paths.os.environ', {'APPDATA': r'C:\Users\test\AppData\Roaming'})
    def test_frozen_mode_uses_appdata(self):
        assert config_dir() == Path(r'C:\Users\test\AppData\Roaming\iOSPrintServer')

    @patch('app.core._paths.os.environ', {})
    @patch('app.core._paths.Path.home', return_value=Path(r'C:\Users\test'))
    def test_fallback_to_home(self, mock_home):
        from app.core._paths import config_dir

        result = config_dir()
        assert result == Path(r'C:\Users\test\iOSPrintServer')


class TestPersistentDir:
    @patch('app.core._paths.os.environ', {'LOCALAPPDATA': r'C:\Users\test\AppData\Local'})
    def test_dev_mode_uses_localappdata(self):
        assert persistent_dir() == Path(r'C:\Users\test\AppData\Local\iOSPrintServer')

    @patch('app.core._paths.os.environ', {'LOCALAPPDATA': r'C:\Users\test\AppData\Local'})
    def test_frozen_mode_uses_localappdata(self):
        assert persistent_dir() == Path(r'C:\Users\test\AppData\Local\iOSPrintServer')

    @patch('app.core._paths.os.environ', {})
    @patch('app.core._paths.Path.home', return_value=Path(r'C:\Users\test'))
    def test_fallback_to_home(self, mock_home):
        from app.core._paths import persistent_dir

        result = persistent_dir()
        assert result == Path(r'C:\Users\test\iOSPrintServer')


class TestLogDir:
    @patch('app.core._paths.os.environ', {'PROGRAMDATA': r'C:\ProgramData'})
    def test_log_dir_uses_programdata(self):
        assert log_dir() == Path(r'C:\ProgramData\iOSPrintServer\logs')

    @patch('app.core._paths.os.environ', {})
    def test_log_dir_fallback_to_default(self):
        assert log_dir() == Path(r'C:\ProgramData\iOSPrintServer\logs')
