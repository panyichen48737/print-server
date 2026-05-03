"""开机自启管理 — 使用 Windows Task Scheduler（优于注册表 Run 键）"""
import os
import sys
import subprocess
import logging

logger = logging.getLogger('print_server')

TASK_NAME = 'iOSPrintServer'


def _get_python_cmd():
    """获取启动命令"""
    this_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" --start'
    else:
        return f'"{sys.executable}" -m console --start'


def is_autostart_installed():
    """检查任务计划是否存在"""
    try:
        r = subprocess.run(
            ['schtasks', '/Query', '/TN', TASK_NAME, '/V', '/FO', 'CSV'],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0 and TASK_NAME in r.stdout
    except Exception:
        return False


def install_autostart():
    """注册开机自启（用户登录时启动守护进程，无窗口，延迟30s）"""
    if is_autostart_installed():
        return True, '开机自启已注册'

    cmd = _get_python_cmd()
    task_cmd = f'cmd /c start /b "" {cmd}'

    try:
        r = subprocess.run([
            'schtasks', '/Create', '/TN', TASK_NAME,
            '/TR', task_cmd,
            '/SC', 'ONLOGON',
            '/DELAY', '0000:30',
            '/IT',           # 仅在用户登录时运行
            '/RL', 'LIMITED', # 普通权限
            '/F',             # 强制覆盖
        ], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            logger.info('开机自启已注册（延迟30秒）')
            return True, '开机自启注册成功'
        else:
            logger.warning(f'schtasks 失败: {r.stderr.strip()}')
            return False, f'注册失败: {r.stderr.strip()}'
    except Exception as e:
        return False, f'注册异常: {e}'


def uninstall_autostart():
    """卸载开机自启"""
    if not is_autostart_installed():
        return True, '开机自启未注册'

    try:
        r = subprocess.run(
            ['schtasks', '/Delete', '/TN', TASK_NAME, '/F'],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            logger.info('开机自启已卸载')
            return True, '开机自启卸载成功'
        else:
            return False, f'卸载失败: {r.stderr.strip()}'
    except Exception as e:
        return False, f'卸载异常: {e}'
