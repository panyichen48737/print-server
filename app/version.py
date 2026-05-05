"""版本号 — 优先从 version.txt 读取（PyInstaller 打包后使用），其次 git tag，最后回退"""
import subprocess
import os
import sys
from pathlib import Path


def _get_version() -> str:
    # 1. 环境变量（最高优先级）
    env_ver = os.environ.get('RELEASE_VERSION')
    if env_ver:
        return env_ver.lstrip('v')

    # 2. version.txt（PyInstaller --add-data 内嵌到 resources/）
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        ver_file = Path(sys._MEIPASS) / 'resources' / 'version.txt'
    else:
        ver_file = Path(__file__).resolve().parent.parent / 'version.txt'
    if ver_file.exists():
        return ver_file.read_text().strip()

    # 3. git describe（开发环境）
    try:
        desc = subprocess.run(
            ['git', 'describe', '--tags', '--always', '--dirty'],
            capture_output=True, text=True, timeout=2,
            cwd=Path(__file__).resolve().parent.parent,
        )
        if desc.returncode == 0 and desc.stdout.strip():
            return desc.stdout.strip().lstrip('v')
    except (OSError, subprocess.TimeoutExpired):
        pass

    return '0.0.0-dev'


__version__: str = _get_version()
