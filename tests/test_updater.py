"""Tests for app/updater.py — version comparison, GitHub API, download."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.version import __version__
from app.updater import (
    _version_greater,
    check_latest_version,
    cleanup_cache,
    download_installer,
    get_installed_version_from_registry,
    install_update,
)


class TestVersionGreater:
    def test_newer_major(self):
        assert _version_greater('2.0.0', '1.6.0')

    def test_newer_minor(self):
        assert _version_greater('1.7.0', '1.6.0')

    def test_newer_patch(self):
        assert _version_greater('1.6.1', '1.6.0')

    def test_equal(self):
        assert not _version_greater('1.6.0', '1.6.0')

    def test_older(self):
        assert not _version_greater('1.5.0', '1.6.0')

    def test_different_lengths(self):
        assert _version_greater('1.10', '1.6.0')

    def test_shorter_older(self):
        assert not _version_greater('1.5', '1.6.0')

    def test_longer_newer(self):
        assert _version_greater('1.6.0.1', '1.6.0')


class TestCheckLatestVersion:
    def _mock_manifest_response(self, data: dict):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(data).encode()
        return mock_resp

    @patch('app.updater.urlopen')
    def test_new_version_with_asset(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_manifest_response(
            {
                'latest_version': '9.9.9',
                'release_url': 'https://github.com/test/release',
                'release_notes': 'New release',
                'download_url': {
                    'incremental': '',
                    'full': 'https://github.com/test/setup.exe',
                },
                'sha256': {
                    'incremental': '',
                    'full': 'abc123',
                },
            }
        )

        info = check_latest_version()
        assert info is not None
        assert info.latest_version == '9.9.9'
        assert info.is_newer is True
        assert info.download_url == 'https://github.com/test/setup.exe'
        assert info.download_type == 'full'
        assert info.release_url == 'https://github.com/test/release'

    @patch('app.updater.urlopen')
    def test_prefers_incremental_zip(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_manifest_response(
            {
                'latest_version': '9.9.9',
                'release_url': 'https://github.com/test/release',
                'release_notes': '',
                'download_url': {
                    'incremental': 'https://x/update.zip',
                    'full': 'https://x/setup.exe',
                },
                'sha256': {'incremental': 'def456', 'full': 'abc123'},
            }
        )
        info = check_latest_version()
        assert info is not None
        assert info.download_url == 'https://x/update.zip'
        assert info.download_type == 'incremental'

    @patch('app.updater.urlopen')
    def test_same_version_no_asset(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_manifest_response(
            {
                'latest_version': __version__,
                'release_url': '',
                'release_notes': '',
                'download_url': {'incremental': '', 'full': ''},
                'sha256': {'incremental': '', 'full': ''},
            }
        )

        info = check_latest_version()
        assert info is not None
        assert info.is_newer is False
        assert info.download_url is None

    @patch('app.updater.urlopen', side_effect=OSError('timeout'))
    def test_network_error_returns_none(self, mock_urlopen):
        assert check_latest_version() is None

    @patch('app.updater.urlopen')
    def test_no_tag_name_returns_none(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_manifest_response({'latest_version': ''})
        assert check_latest_version() is None

    @patch('app.updater.urlopen')
    def test_asset_filter_ignores_other_files(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_manifest_response(
            {
                'latest_version': '9.9.9',
                'release_url': '',
                'release_notes': '',
                'download_url': {
                    'incremental': '',
                    'full': 'https://x/setup.exe',
                },
                'sha256': {'incremental': '', 'full': 'abc123'},
            }
        )

        info = check_latest_version()
        assert info is not None
        assert info.download_url == 'https://x/setup.exe'
        assert info.download_type == 'full'


class TestDownloadInstaller:
    def _mock_download_response(self, data: bytes, content_length: int | None = None):
        mock_resp = MagicMock()
        mock_resp.read.side_effect = [data, b'']
        if content_length is not None:
            mock_resp.headers = {'Content-Length': str(content_length)}
        else:
            mock_resp.headers = {}
        return mock_resp

    @patch('app.updater.urlopen')
    def test_download_success(self, mock_urlopen, tmp_path):
        data = b'fake installer content'
        mock_urlopen.return_value = self._mock_download_response(data, len(data))

        dest = tmp_path / 'setup.exe'
        result = download_installer('https://x/setup.exe', dest)
        assert result is True
        assert dest.read_bytes() == data

    @patch('app.updater.urlopen')
    def test_download_calls_progress(self, mock_urlopen, tmp_path):
        data = b'progress test data'
        mock_urlopen.return_value = self._mock_download_response(data, len(data))

        dest = tmp_path / 'setup.exe'
        calls = []

        def on_progress(d, t):
            calls.append((d, t))

        result = download_installer('https://x/setup.exe', dest, on_progress)
        assert result is True
        assert len(calls) > 0
        assert calls[-1] == (len(data), len(data))

    @patch('app.updater.urlopen', side_effect=OSError('timeout'))
    def test_download_failure_cleans_up(self, mock_urlopen, tmp_path):
        dest = tmp_path / 'setup.exe'
        dest.touch()
        result = download_installer('https://x/setup.exe', dest)
        assert result is False
        assert not dest.exists()

    @patch('app.updater.urlopen')
    def test_download_no_content_length(self, mock_urlopen, tmp_path):
        data = b'no content-length'
        mock_urlopen.return_value = self._mock_download_response(data, None)

        dest = tmp_path / 'setup.exe'
        calls = []

        result = download_installer('https://x/setup.exe', dest, lambda d, t: calls.append((d, t)))
        assert result is True
        assert len(calls) == 0


class TestInstallUpdate:
    @patch('subprocess.Popen')
    @patch('threading.Timer')
    def test_spawns_installer_and_exits(self, mock_timer, mock_popen):
        result = install_update(Path('/fake/setup.exe'))
        assert result is True
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert str(args[0]).endswith('setup.exe')
        assert args[1] == '/S'

    @patch('subprocess.Popen', side_effect=OSError)
    def test_install_failure_returns_false(self, mock_popen):
        result = install_update(Path('/fake/setup.exe'))
        assert result is False


class TestCleanupCache:
    def test_removes_old_files(self, tmp_path):
        old = tmp_path / 'iOSPrintServer-Setup-1.5.0.exe'
        new = tmp_path / 'iOSPrintServer-Setup-1.6.0.exe'
        old.touch()
        import time

        time.sleep(0.02)
        new.touch()

        cleanup_cache(tmp_path, keep_latest=1)
        assert new.exists()
        assert not old.exists()

    def test_no_files_does_nothing(self, tmp_path):
        cleanup_cache(tmp_path)

    def test_non_existent_dir(self):
        cleanup_cache(Path('/nonexistent'))


class TestGetInstalledVersionFromRegistry:
    @patch('builtins.__import__')
    def test_reads_version(self, mock_builtins_import):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = 'fake_key'
        mock_winreg.QueryValueEx.return_value = ('1.6.0', 1)

        def fake_import(name, *args, **kwargs):
            if name == 'winreg':
                return mock_winreg
            return __import__(name, *args, **kwargs)

        mock_builtins_import.side_effect = fake_import

        result = get_installed_version_from_registry()
        assert result == '1.6.0'
        mock_winreg.OpenKey.assert_called_once()
        mock_winreg.QueryValueEx.assert_called_once_with('fake_key', 'DisplayVersion')

    @patch('builtins.__import__')
    def test_no_key_returns_none(self, mock_builtins_import):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = OSError

        def fake_import(name, *args, **kwargs):
            if name == 'winreg':
                return mock_winreg
            return __import__(name, *args, **kwargs)

        mock_builtins_import.side_effect = fake_import

        assert get_installed_version_from_registry() is None
