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


DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'server_daemon.py')


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
    """检查守护进程是否存活（直接检查 server_daemon PID）"""
    status = read_daemon_status()
    pid = status.get('pid')
    if not pid or status.get('status') != 'running':
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
        CREATE_NO_WINDOW = 0x08000000
        # 冻结 EXE 模式下没有 .py 入口，直接用 --server-daemon 调自己
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, '--server-daemon']
            cwd = os.path.dirname(sys.executable)
        else:
            cmd = [sys.executable, DAEMON_SCRIPT]
            cwd = os.path.dirname(DAEMON_SCRIPT)
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            creationflags=CREATE_NO_WINDOW,
            stdout=open(log_dir / 'daemon_stdout.log', 'a'),
            stderr=open(log_dir / 'daemon_stderr.log', 'a'),
        )
        # 轮询等待 server_daemon 写入 daemon.json
        for _ in range(12):
            if is_daemon_alive():
                return True, f'守护进程已启动 (PID: {proc.pid})'
            time.sleep(0.5)
        return False, '守护进程启动超时'
    except Exception as e:
        return False, f'启动失败: {e}'


def stop_daemon():
    """停止后台守护进程"""
    if not is_daemon_alive():
        _cleanup_json()
        return True, '守护进程未运行'

    status = read_daemon_status()
    server_pid = status.get('pid')

    try:
        # 写入主动关闭标记
        f_daemon = _daemon_json_path()
        try:
            f_daemon.write_text(json.dumps({'status': 'stopped', 'pid': server_pid}, ensure_ascii=False))
        except Exception:
            pass

        # 终止后台工作进程 — 优先 graceful
        if server_pid:
            try:
                os.kill(server_pid, signal.CTRL_BREAK_EVENT)
                time.sleep(3)
            except Exception:
                pass
            try:
                os.kill(server_pid, 0)
                subprocess.run(['taskkill', '/F', '/PID', str(server_pid)],
                               capture_output=True, timeout=5, check=False)
            except (OSError, PermissionError):
                pass

        _cleanup_json()
        return True, '守护进程已停止'
    except Exception as e:
        return False, f'停止失败: {e}'


def restart_daemon():
    """重启守护进程"""
    ok, msg = stop_daemon()
    time.sleep(1)
    return start_daemon()


def _cleanup_json():
    for path_fn in [_daemon_json_path]:
        f = path_fn()
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass
