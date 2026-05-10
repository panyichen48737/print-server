"""版本号 — 优先从 version.txt 读取（PyInstaller 打包后使用），其次 git tag，最后回退"""

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path


def _version_file() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'resources' / 'version.txt'
    return Path(__file__).resolve().parent.parent.parent / 'version.txt'


def _manifest_file() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'resources' / 'version_info.json'
    return Path(__file__).resolve().parent.parent.parent / 'build' / 'resources' / 'version_info.json'


def _get_version() -> str:
    env_ver = os.environ.get('RELEASE_VERSION')
    if env_ver:
        return env_ver.lstrip('v')

    ver_file = _version_file()
    if ver_file.exists():
        return ver_file.read_text().strip()

    try:
        desc = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=Path(__file__).resolve().parent.parent.parent,
        )
        if desc.returncode == 0 and desc.stdout.strip():
            return desc.stdout.strip().lstrip('v')
    except (OSError, subprocess.TimeoutExpired):
        pass

    return '0.0.0-dev'


def _get_build_date() -> str:
    ver_file = _version_file()
    if ver_file.exists():
        try:
            ts = ver_file.stat().st_mtime
            return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        except OSError:
            pass
    return 'unknown'


def _get_pyinstaller_version() -> str:
    try:
        from importlib.metadata import version as pkg_version
        return pkg_version('pyinstaller')
    except Exception:
        return 'unknown'


def get_build_manifest() -> dict:
    """Return build version manifest dict, or empty dict if unavailable."""
    mf = _manifest_file()
    if mf.exists():
        try:
            return json.loads(mf.read_text())
        except Exception:
            pass
    return {}


__version__: str = _get_version()
__build_date__: str = _get_build_date()
__pyinstaller_version__: str = _get_pyinstaller_version()
