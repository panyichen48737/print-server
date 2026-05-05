"""开机自启管理

策略（按管理员状态自动选择）：
  管理员 → pywin32 注册为 Windows 服务
          任务管理器「服务」面板可见，开机自启，崩溃自动重启，sc query 正确显示状态
  非管理员 → 启动文件夹快捷方式
            任务管理器「启动」页面可见，开机登录后启动
"""
import os
import subprocess
import sys
from pathlib import Path

import win32service
import win32serviceutil
from loguru import logger

SERVICE_NAME = 'iOSPrintServer'
SERVICE_DISPLAY_NAME = 'iOS 云打印服务器'
STARTUP_LINK_NAME = 'iOSPrintServer.lnk'


def _service_command() -> str:
    """Windows 服务二进制路径（含 --server-daemon --service 参数）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return f'"{sys.executable}" --server-daemon --service'
    this_dir = Path(__file__).resolve().parent.parent
    entry = this_dir / 'console_app.py'
    return f'"{sys.executable}" "{entry}" --server-daemon --service'


def _is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _startup_folder() -> Path:
    return Path(os.environ.get(
        'APPDATA', os.path.expanduser('~'),
    )) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'


def _exe_path() -> str:
    """当前可执行文件路径（打包模式）或 python+脚本路径（开发模式）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return sys.executable
    this_dir = Path(__file__).resolve().parent.parent
    daemon = this_dir / 'app' / 'server_daemon.py'
    return f'"{sys.executable}" "{daemon}"'


# ── 公开 API ──


def is_autostart_installed() -> bool:
    if _is_admin():
        return _service_installed()
    return _startup_link_exists()


def install_autostart() -> tuple[bool, str]:
    if is_autostart_installed():
        return True, '开机自启已注册'
    if _is_admin():
        return _install_service()
    return _install_startup_link()


def uninstall_autostart() -> tuple[bool, str]:
    removed = False
    if _service_installed():
        ok, _ = _uninstall_service()
        removed = removed or ok
    if _startup_link_exists():
        _remove_startup_link()
        removed = True
    return (True, '开机自启已卸载') if removed else (True, '开机自启未注册')


# ── Windows 服务（pywin32） ──


def _service_installed() -> bool:
    try:
        win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return True
    except win32service.error:
        return False


def _service_running() -> bool:
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return status[1] == win32service.SERVICE_RUNNING
    except win32service.error:
        return False


def _install_service() -> tuple[bool, str]:
    try:
        if getattr(sys, 'frozen', False):
            # Frozen EXE: 二进制是 exe 自身，带 --server-daemon --service 参数
            cmd = f'"{sys.executable}" --server-daemon --service'
        else:
            # 开发模式：由 pythonservice.exe 托管 Python 服务类
            cmd = None

        kwargs = dict(
            serviceName=SERVICE_NAME,
            displayName=SERVICE_DISPLAY_NAME,
            startType=win32service.SERVICE_AUTO_START,
        )
        if cmd:
            kwargs['exeName'] = cmd

        # 移除已存在的服务（如果有旧版本残留）
        try:
            win32serviceutil.RemoveService(SERVICE_NAME)
        except Exception:
            pass

        win32serviceutil.InstallService('app.win_service.DaemonService', **kwargs)

        # 崩溃自动重启
        for action in ('restart/5000', 'restart/10000', 'restart/30000'):
            subprocess.run(
                ['sc', 'failure', SERVICE_NAME, 'actions=', action, 'reset=', '86400'],
                capture_output=True, timeout=5,
            )

        # 启动服务
        win32serviceutil.StartService(SERVICE_NAME)

        logger.info('Windows 服务已注册并启动')
        return True, '开机自启注册成功（Windows 服务 — 任务管理器「服务」面板可见）'
    except Exception as e:
        return False, f'服务注册异常: {e}'


def _uninstall_service() -> tuple[bool, str]:
    try:
        try:
            win32serviceutil.StopService(SERVICE_NAME)
        except Exception:
            pass
        win32serviceutil.RemoveService(SERVICE_NAME)
        logger.info('Windows 服务已卸载')
        return True, 'Windows 服务已卸载'
    except Exception as e:
        return False, f'服务卸载异常: {e}'


# ── 启动文件夹快捷方式 ──


def _startup_link_path() -> Path:
    return _startup_folder() / STARTUP_LINK_NAME


def _startup_link_exists() -> bool:
    return _startup_link_path().is_file()


def _install_startup_link() -> tuple[bool, str]:
    exe = _exe_path()
    link = _startup_link_path()
    try:
        _startup_folder().mkdir(parents=True, exist_ok=True)
        ps_script = ('$ws = New-Object -ComObject WScript.Shell; '
                     f'$s = $ws.CreateShortcut(\'{link}\'); '
                     f'$s.TargetPath = \'{exe}\'; '
                     '$s.Arguments = \'--server-daemon\'; '
                     f'$s.WorkingDirectory = \'{os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()}\'; '
                     '$s.Save()')
        subprocess.run(['powershell', '-NoProfile', '-Command', ps_script],
                       capture_output=True, timeout=15, check=True)
        logger.info('开机自启快捷方式已创建')
        return True, '开机自启注册成功（启动文件夹 — 任务管理器「启动」页面可见）'
    except Exception as e:
        return False, f'快捷方式创建失败: {e}'


def _remove_startup_link():
    try:
        _startup_link_path().unlink(missing_ok=True)
        logger.info('开机自启快捷方式已删除')
    except Exception:
        pass
