"""开机自启管理 — 优先 nssm Windows Service，回退 schtasks"""
import os
import sys
import shutil
import subprocess
import logging

logger = logging.getLogger('print_server')

SERVICE_NAME = 'iOSPrintServer'
TASK_NAME = 'iOSPrintServer'


def _nssm_path():
    """查找 nssm.exe（打包目录优先，回退 PATH）"""
    # 冻结模式：nssm 在 sys._MEIPASS 中
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            candidate = os.path.join(meipass, 'nssm.exe')
            if os.path.isfile(candidate):
                return candidate
    # 开发模式：项目 bin 目录
    local = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin', 'nssm.exe')
    if os.path.isfile(local):
        return local
    # 系统 PATH
    which = shutil.which('nssm')
    if which:
        return which
    return None


def _nssm_available():
    return _nssm_path() is not None


def _project_root():
    """项目根目录"""
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            return meipass
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_python_cmd():
    """获取 schtasks 用启动命令"""
    this_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}" --start'
    else:
        return f'"{sys.executable}" "{this_dir}\\guardian.py"'


def is_autostart_installed():
    """检查是否已注册自启（nssm 服务优先）"""
    if _nssm_available():
        try:
            r = subprocess.run(['nssm', 'status', SERVICE_NAME],
                               capture_output=True, timeout=5)
            if 'SERVICE_RUNNING' in r.stdout.decode('utf-8', errors='ignore') or \
               'SERVICE_STOPPED' in r.stdout.decode('utf-8', errors='ignore') or \
               'SERVICE_PAUSED' in r.stdout.decode('utf-8', errors='ignore'):
                return True
        except Exception:
            pass
    try:
        r = subprocess.run(
            ['schtasks', '/Query', '/TN', TASK_NAME, '/V', '/FO', 'CSV'],
            capture_output=True, text=True, timeout=10
        )
        return r.returncode == 0 and TASK_NAME in r.stdout
    except Exception:
        return False


def install_autostart():
    """注册开机自启 — 优先 nssm Windows Service，回退 schtasks"""
    if is_autostart_installed():
        return True, '开机自启已注册'

    if _nssm_available():
        return _install_nssm()
    else:
        return _install_schtasks()


def _install_nssm():
    """通过 nssm 注册为 Windows Service（系统级，开机自启，崩溃自动重启）"""
    nssm = _nssm_path()
    try:
        project_root = _project_root()
        python_exe = sys.executable
        guardian_script = os.path.join(project_root, 'guardian.py')

        r = subprocess.run(
            [nssm, 'install', SERVICE_NAME, python_exe, guardian_script],
            capture_output=True, timeout=15
        )
        if r.returncode != 0:
            return False, f'nssm 安装失败: {r.stderr.decode("utf-8", errors="ignore").strip()}'

        subprocess.run([nssm, 'set', SERVICE_NAME, 'AppDirectory', project_root],
                       capture_output=True, timeout=5)
        subprocess.run([nssm, 'set', SERVICE_NAME, 'DisplayName', 'iOS 云打印服务器'],
                       capture_output=True, timeout=5)
        subprocess.run([nssm, 'set', SERVICE_NAME, 'Description',
                       'iOS 云打印服务器后台守护进程，崩溃自动重启'],
                       capture_output=True, timeout=5)
        subprocess.run([nssm, 'set', SERVICE_NAME, 'Start', 'SERVICE_AUTO_START'],
                       capture_output=True, timeout=5)
        subprocess.run([nssm, 'set', SERVICE_NAME, 'AppRotateFiles', '1'],
                       capture_output=True, timeout=5)
        subprocess.run([nssm, 'set', SERVICE_NAME, 'AppRotateOnline', '1'],
                       capture_output=True, timeout=5)
        subprocess.run([nssm, 'set', SERVICE_NAME, 'AppExit', 'Default', 'Exit'],
                       capture_output=True, timeout=5)
        for code in ('0', '1', '2'):
            subprocess.run([nssm, 'set', SERVICE_NAME, 'AppExit', code, 'Restart'],
                           capture_output=True, timeout=5)

        subprocess.run([nssm, 'start', SERVICE_NAME], capture_output=True, timeout=15)

        logger.info('Windows Service 已注册并启动（nssm）')
        return True, '开机自启注册成功（Windows Service）'
    except Exception as e:
        return False, f'nssm 注册异常: {e}'


def _install_schtasks():
    """回退方案：通过 schtasks 注册开机自启"""
    cmd = _get_python_cmd()
    task_cmd = f'cmd /c start /b "" {cmd}'

    try:
        r = subprocess.run([
            'schtasks', '/Create', '/TN', TASK_NAME,
            '/TR', task_cmd,
            '/SC', 'ONLOGON',
            '/DELAY', '0000:30',
            '/IT',
            '/RL', 'LIMITED',
            '/F',
        ], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            logger.info('开机自启已注册（schtasks，延迟30秒）')
            return True, '开机自启注册成功（schtasks）'
        else:
            return False, f'schtasks 失败: {r.stderr.strip()}'
    except Exception as e:
        return False, f'schtasks 异常: {e}'


def uninstall_autostart():
    """卸载开机自启"""
    removed = False
    nssm = _nssm_path()

    if nssm:
        try:
            subprocess.run([nssm, 'stop', SERVICE_NAME],
                           capture_output=True, timeout=10)
            r = subprocess.run([nssm, 'remove', SERVICE_NAME, 'confirm'],
                               capture_output=True, timeout=10)
            if r.returncode == 0:
                removed = True
                logger.info('Windows Service 已卸载')
        except Exception:
            pass

    try:
        r = subprocess.run(
            ['schtasks', '/Delete', '/TN', TASK_NAME, '/F'],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            removed = True
            logger.info('schtasks 自启已卸载')
    except Exception:
        pass

    return (True, '开机自启已卸载') if removed else (True, '开机自启未注册')
