"""版本号 — 自动从 git tag 获取"""
import subprocess
import os
from pathlib import Path


def _get_version() -> str:
    # CI/构建时通过环境变量注入精确版本
    env_ver = os.environ.get('RELEASE_VERSION')
    if env_ver:
        return env_ver.lstrip('v')

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
