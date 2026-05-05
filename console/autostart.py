"""开机自启管理 — 启动文件夹快捷方式（现代桌面应用标准方式）

所有用户统一使用启动文件夹，不再注册 Windows Service。
大多数桌面应用（如 Discord、Steam、VS Code）都使用此方式。
"""

import os
import subprocess
import sys
from pathlib import Path

from loguru import logger

STARTUP_LINK_NAME = 'iOSPrintServer.lnk'


def _startup_folder() -> Path:
    return (
        Path(
            os.environ.get(
                'APPDATA',
                os.path.expanduser('~'),
            )
        )
        / 'Microsoft'
        / 'Windows'
        / 'Start Menu'
        / 'Programs'
        / 'Startup'
    )


def _exe_path() -> tuple[str, str]:
    """返回 (可执行路径, 参数)"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return sys.executable, '--headless'
    this_dir = Path(__file__).resolve().parent.parent
    return sys.executable, f'"{this_dir}" -m console --headless'


def _startup_link_path() -> Path:
    return _startup_folder() / STARTUP_LINK_NAME


def _startup_link_exists() -> bool:
    return _startup_link_path().is_file()


def is_autostart_installed() -> bool:
    return _startup_link_exists()


def install_autostart() -> tuple[bool, str]:
    if _startup_link_exists():
        return True, '开机自启已注册'

    exe, args = _exe_path()
    link = _startup_link_path()
    try:
        _startup_folder().mkdir(parents=True, exist_ok=True)
        ps_script = (
            '$ws = New-Object -ComObject WScript.Shell; '
            f"$s = $ws.CreateShortcut('{link}'); "
            f"$s.TargetPath = '{exe}'; "
            f"$s.Arguments = '{args}'; "
            f"$s.WorkingDirectory = '{os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.getcwd()}'; "
            '$s.Save()'
        )
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True,
            timeout=15,
            check=True,
        )
        logger.info('开机自启快捷方式已创建')
        msg = '开机自启注册成功（启动文件夹 — 任务管理器「启动」页面可见）'
        return True, msg
    except Exception as e:
        return False, f'快捷方式创建失败: {e}'


def uninstall_autostart() -> tuple[bool, str]:
    try:
        _startup_link_path().unlink(missing_ok=True)
        logger.info('开机自启快捷方式已删除')
        return True, '开机自启已卸载'
    except Exception as e:
        return False, f'卸载失败: {e}'
