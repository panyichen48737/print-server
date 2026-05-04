"""开机自启管理

策略（按管理员状态自动选择）：
  管理员 → sc.exe 注册为 Windows 服务
          任务管理器「服务」面板可见，开机自启，崩溃自动重启
  非管理员 → 启动文件夹快捷方式
            任务管理器「启动」页面可见，开机登录后启动
"""
import os
import sys
import subprocess
from pathlib import Path
from loguru import logger

SERVICE_NAME = 'iOSPrintServer'
SERVICE_DISPLAY_NAME = 'iOS 云打印服务器'
STARTUP_LINK_NAME = 'iOSPrintServer.lnk'


def _exe_path() -> str:
    """当前可执行文件路径（打包模式）或 python+脚本路径（开发模式）"""
    if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
        return sys.executable
    # 开发模式下通过 python server_daemon.py 启动
    this_dir = Path(__file__).resolve().parent.parent
    daemon = this_dir / 'app' / 'server_daemon.py'
    return f'"{sys.executable}" "{daemon}"'


def _is_admin() -> bool:
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def _startup_folder() -> Path:
    """当前用户的「启动」文件夹路径"""
    return Path(os.environ.get(
        'APPDATA',
        os.path.expanduser('~'),
    )) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'


# ── 公开 API ──


def is_autostart_installed() -> bool:
    """检测是否已注册自启"""
    if _is_admin():
        return _service_installed()
    return _startup_link_exists()


def install_autostart() -> tuple[bool, str]:
    """注册开机自启"""
    if is_autostart_installed():
        return True, '开机自启已注册'

    if _is_admin():
        return _install_service()
    return _install_startup_link()


def uninstall_autostart() -> tuple[bool, str]:
    """卸载开机自启"""
    removed = False
    if _service_installed():
        ok, _ = _uninstall_service()
        removed = removed or ok
    if _startup_link_exists():
        _remove_startup_link()
        removed = True
    return (True, '开机自启已卸载') if removed else (True, '开机自启未注册')


# ── Windows 服务（sc.exe） ──


def _service_installed() -> bool:
    try:
        r = subprocess.run(
            ['sc', 'query', SERVICE_NAME],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and 'STATE' in r.stdout
    except Exception:
        return False


def _install_service() -> tuple[bool, str]:
    exe = _exe_path()
    try:
        # 创建服务
        r = subprocess.run([
            'sc', 'create', SERVICE_NAME,
            'binPath=', f'{exe} --server-daemon',
            'displayName=', SERVICE_DISPLAY_NAME,
            'start=', 'auto',
            'type=', 'own',
            'error=', 'normal',
        ], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return False, f'服务创建失败: {r.stderr.strip() or r.stdout.strip()}'

        # 崩溃自动重启（失败后等待 5 秒重启，最多重启 3 次）
        for action in ('restart/5000', 'restart/10000', 'restart/30000'):
            subprocess.run([
                'sc', 'failure', SERVICE_NAME,
                'actions=', action,
                'reset=', '86400',
            ], capture_output=True, timeout=5)

        # 启动服务
        subprocess.run(['sc', 'start', SERVICE_NAME],
                       capture_output=True, timeout=15)

        logger.info('Windows 服务已注册并启动')
        return True, '开机自启注册成功（Windows 服务 — 任务管理器「服务」面板可见）'
    except Exception as e:
        return False, f'服务注册异常: {e}'


def _uninstall_service() -> tuple[bool, str]:
    try:
        subprocess.run(['sc', 'stop', SERVICE_NAME],
                       capture_output=True, timeout=10)
        subprocess.run(['sc', 'delete', SERVICE_NAME],
                       capture_output=True, timeout=10)
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
        # 用 PowerShell 创建 .lnk 快捷方式
        ps_script = f'''
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{link}')
$s.TargetPath = '{exe}'
$s.Arguments = '--server-daemon'
$s.WorkingDirectory = '{os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()}'
$s.Save()
'''
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
