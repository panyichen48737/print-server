"""自安装模块：启动时将程序复制到专属目录，创建开始菜单和开机自启快捷方式

流程：
  1. 检测是否在持久安装目录运行
  2. 若不是，复制 EXE 到安装目录，创建快捷方式，启动新实例后退出
  3. 资源版本不同的覆盖资源（ensure_resources），配置文件永远不覆盖
"""

import os
import subprocess
import sys
from pathlib import Path

from loguru import logger

INSTALL_DIR_NAME = 'iOSPrintServer'
STARTMENU_DIR_NAME = 'iOSPrintServer'


def install_dir() -> str:
    """程序专属安装目录 — %LOCALAPPDATA%/iOSPrintServer"""
    local_app_data = os.environ.get(
        'LOCALAPPDATA',
        os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), '..', 'Local'),
    )
    return os.path.join(local_app_data, INSTALL_DIR_NAME)


def _start_menu_dir() -> Path:
    return (
        Path(os.environ.get('APPDATA', os.path.expanduser('~')))
        / 'Microsoft'
        / 'Windows'
        / 'Start Menu'
        / 'Programs'
        / STARTMENU_DIR_NAME
    )


def _installed_exe_path() -> str:
    return os.path.join(install_dir(), os.path.basename(sys.executable))


def _is_running_from_install_dir() -> bool:
    """检测当前 EXE 是否已在安装目录中运行"""
    if not getattr(sys, 'frozen', False) and not getattr(sys, '__compiled__', False):
        return True  # 开发模式直接跳过
    exe = sys.executable
    target = _installed_exe_path()
    return os.path.normpath(exe) == os.path.normpath(target)


def _ensure_install_dir() -> None:
    os.makedirs(install_dir(), exist_ok=True)


def _copy_self() -> None:
    """将自身复制到安装目录（Windows 允许复制正在运行的 exe）"""
    src = sys.executable
    dst = _installed_exe_path()
    if os.path.normpath(src) == os.path.normpath(dst):
        return

    _ensure_install_dir()
    try:
        # shutil.copy2 会复制文件元数据
        import shutil

        shutil.copy2(src, dst)
        logger.info(f'程序已复制到: {dst}')
    except Exception as e:
        logger.warning(f'复制程序失败: {e}')
        raise


def ensure_installed() -> bool:
    """确保程序安装在专属目录

    如果不在安装目录运行，复制自身并启动新实例，然后退出当前进程。
    返回 True 表示「已安装可继续」，返回 False 表示「已启动新实例应退出」。
    """
    if not getattr(sys, 'frozen', False) and not getattr(sys, '__compiled__', False):
        return True  # 开发模式不处理

    if _is_running_from_install_dir():
        return True  # 已在安装目录，继续

    try:
        _copy_self()
        _ensure_start_menu()
        # 启动安装目录中的新实例
        exe = _installed_exe_path()
        args = '--server-daemon' if '--server-daemon' in sys.argv else ''
        logger.info(f'启动安装目录中的程序: {exe} {args}')
        subprocess.Popen(
            [exe] + (['--server-daemon'] if '--server-daemon' in sys.argv else []),
            close_fds=True,
        )
        return False  # 通知调用方退出当前进程
    except Exception as e:
        logger.error(f'自安装失败: {e}')
        return True  # 安装失败也继续（容错）


def _ensure_start_menu() -> None:
    """创建开始菜单快捷方式（如果不存在或版本不同）"""
    link_dir = _start_menu_dir()
    link_path = link_dir / 'iOSPrintServer.lnk'

    tag_file = link_dir / '.version'
    current_version = _read_app_version()

    # 检查快捷方式是否已存在且版本一致
    if link_path.is_file() and tag_file.is_file():
        existing = tag_file.read_text(encoding='utf-8').strip()
        if existing == current_version:
            return

    link_dir.mkdir(parents=True, exist_ok=True)
    exe = _installed_exe_path() if getattr(sys, 'frozen', False) else sys.executable
    workdir = os.path.dirname(exe) if getattr(sys, 'frozen', False) else os.getcwd()

    try:
        ps_script = (
            '$ws = New-Object -ComObject WScript.Shell; '
            f"$s = $ws.CreateShortcut('{link_path}'); "
            f"$s.TargetPath = '{exe}'; "
            f"$s.Arguments = '--server-daemon'; "
            f"$s.WorkingDirectory = '{workdir}'; "
            f"$s.Description = 'iOS 云打印服务器'; "
            '$s.Save()'
        )
        subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True,
            timeout=15,
            check=True,
        )
        tag_file.write_text(current_version, encoding='utf-8')
        logger.info(f'开始菜单快捷方式已创建: {link_path}')
    except Exception as e:
        logger.warning(f'开始菜单快捷方式创建失败: {e}')


def _read_app_version() -> str:
    """读取应用版本号"""
    try:
        from app.version import __version__

        return __version__
    except ImportError:
        return '1.0.0'
