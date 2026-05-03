"""守护进程管理 — 通过子进程启动/停止/监控后台服务器"""
import os
import sys
import json
import time
import signal
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger('print_server')


DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server_daemon.py')


def _daemon_json_path():
    from app._paths import app_root
    return Path(app_root()) / 'logs' / 'daemon.json'


def read_daemon_status():
    """读取守护进程状态 JSON"""
    f = _daemon_json_path()
    if not f.exists():
        return {'status': 'stopped', 'pid': None}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {'status': 'stopped', 'pid': None}


def is_daemon_alive():
    """检查守护进程是否存活"""
    status = read_daemon_status()
    pid = status.get('pid')
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def start_daemon():
    """以隐藏控制台窗口启动后台守护进程"""
    if is_daemon_alive():
        return True, '守护进程已在运行'

    from app._paths import app_root
    log_dir = Path(app_root()) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 使用 CREATE_NO_WINDOW 标志启动无窗口进程
        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            [sys.executable, DAEMON_SCRIPT],
            cwd=os.path.dirname(DAEMON_SCRIPT),
            creationflags=CREATE_NO_WINDOW,
            stdout=open(log_dir / 'daemon_stdout.log', 'a'),
            stderr=open(log_dir / 'daemon_stderr.log', 'a'),
        )
        # 等待几秒确认启动
        time.sleep(2)
        if is_daemon_alive():
            return True, f'守护进程已启动 (PID: {proc.pid})'
        else:
            return False, '守护进程启动失败'
    except Exception as e:
        return False, f'启动失败: {e}'


def stop_daemon():
    """停止后台守护进程"""
    if not is_daemon_alive():
        _cleanup_status()
        return True, '守护进程未运行'

    status = read_daemon_status()
    pid = status.get('pid')

    try:
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=5)
        time.sleep(1)
        _cleanup_status()
        return True, f'守护进程已停止 (PID: {pid})'
    except Exception as e:
        return False, f'停止失败: {e}'


def restart_daemon():
    """重启守护进程"""
    ok, msg = stop_daemon()
    time.sleep(1)
    return start_daemon()


def _cleanup_status():
    f = _daemon_json_path()
    try:
        if f.exists():
            f.unlink()
    except Exception:
        pass
