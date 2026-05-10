"""Update checker and installer — GitHub Releases API + NSIS silent install."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.core.version import __version__

_GITHUB_API = 'https://api.github.com/repos/panyichen48737/print-server/releases/latest'
_USER_AGENT = 'iOSPrintServer'
_DOWNLOAD_TIMEOUT = 300
_CHUNK_SIZE = 8192


@dataclass
class UpdateInfo:
    latest_version: str
    download_url: str | None
    download_type: str | None  # "incremental" | "full" | None
    release_url: str
    release_notes: str
    is_newer: bool


def _version_greater(a: str, b: str) -> bool:
    """Compare two semver strings. Returns True if a > b."""
    pa = [int(x) for x in a.split('.')]
    pb = [int(x) for x in b.split('.')]
    for i in range(max(len(pa), len(pb))):
        va = pa[i] if i < len(pa) else 0
        vb = pb[i] if i < len(pb) else 0
        if va != vb:
            return va > vb
    return False


def check_latest_version() -> UpdateInfo | None:
    """Query GitHub Releases for latest version. Returns None on error."""
    try:
        req = Request(
            _GITHUB_API,
            headers={
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': _USER_AGENT,
            },
        )
        resp = urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        latest = data.get('tag_name', '').lstrip('v')
        if not latest:
            return None

        # Prefer incremental update zip, fall back to full installer
        incremental_url = next(
            (
                a['browser_download_url']
                for a in data.get('assets', [])
                if a['name'].startswith('update-') and a['name'].endswith('.zip')
            ),
            None,
        )
        full_url = next(
            (
                a['browser_download_url']
                for a in data.get('assets', [])
                if a['name'].startswith('iOSPrintServer-Setup-') and a['name'].endswith('.exe')
            ),
            None,
        )

        if incremental_url:
            download_url = incremental_url
            download_type: str | None = 'incremental'
        else:
            download_url = full_url
            download_type = 'full' if full_url else None

        is_newer = _version_greater(latest, __version__)
        return UpdateInfo(
            latest_version=latest,
            download_url=download_url,
            download_type=download_type,
            release_url=data.get('html_url', ''),
            release_notes=data.get('body', ''),
            is_newer=is_newer,
        )
    except (URLError, json.JSONDecodeError, ValueError, OSError):
        return None


def download_installer(url: str, dest: Path, progress_callback=None) -> bool:
    """Download installer in chunks with progress reporting."""
    try:
        req = Request(url, headers={'User-Agent': _USER_AGENT})
        resp = urlopen(req, timeout=_DOWNLOAD_TIMEOUT)
        total = int(resp.headers.get('Content-Length', 0))
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, 'wb') as f:
            while True:
                chunk = resp.read(_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total:
                    progress_callback(downloaded, total)
        return True
    except (URLError, OSError):
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


def install_update(installer_path: Path) -> bool:
    """Spawn NSIS installer in silent mode, then exit current process."""
    try:
        subprocess.Popen(
            [str(installer_path), '/S'],
            shell=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        # Give installer a moment to start, then hard-exit so NSIS can overwrite files
        threading.Timer(1.0, lambda: os._exit(0)).start()
        return True
    except OSError:
        return False


def cleanup_cache(cache_dir: Path, keep_latest: int = 2) -> None:
    """Remove old installer files, keeping the N most recent."""
    if not cache_dir.is_dir():
        return
    files = sorted(
        cache_dir.glob('iOSPrintServer-Setup-*.exe'),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    for f in files[keep_latest:]:
        f.unlink(missing_ok=True)


def get_installed_version_from_registry() -> str | None:
    """Read DisplayVersion from NSIS uninstall registry key."""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'Software\Microsoft\Windows\CurrentVersion\Uninstall\iOS 云打印服务器',
        )
        version, _ = winreg.QueryValueEx(key, 'DisplayVersion')
        winreg.CloseKey(key)
        return version
    except (OSError, ImportError):
        return None
