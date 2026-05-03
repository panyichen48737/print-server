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


GUARDIAN_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'guardian.py')


def _daemon_json_path():
    from app._paths import app_root
    return Path(app_root()) / 'logs' / 'daemon.json'


def _guardian_json_path():
    from app._paths import app_root
    return Path(app_root()) / 'logs' / 'guardian.json'


def read_daemon_status():
    """读取守护进程状态 JSON"""
    f = _daemon_json_path()
    if not f.exists():
        return {'status': 'stopped', 'pid': None}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {'status': 'stopped', 'pid': None}


def _read_guardian_pid():
    """读取 guardian 守护进程 PID"""
    f = _guardian_json_path()
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text()).get('guardian_pid')
    except Exception:
        return None


def is_daemon_alive():
    """检查守护进程是否存活（检查 guardian 进程）"""
    pid = _read_guardian_pid()
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, PermissionError):
        return False


def start_daemon():
    """以隐藏控制台窗口启动后台守护进程（通过 guardian 看门狗）"""
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
            cmd = [sys.executable, GUARDIAN_SCRIPT]
            cwd = os.path.dirname(GUARDIAN_SCRIPT)
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            creationflags=CREATE_NO_WINDOW,
            stdout=open(log_dir / 'daemon_stdout.log', 'a'),
            stderr=open(log_dir / 'daemon_stderr.log', 'a'),
        )
        # 轮询等待 guardian 启动并写入 PID，替代固定 sleep
        for _ in range(12):
            if is_daemon_alive():
                return True, f'守护进程已启动 (guardian PID: {proc.pid})'
            time.sleep(0.5)
        return False, '守护进程启动超时'
    except Exception as e:
        return False, f'启动失败: {e}'


def stop_daemon():
    """停止后台守护进程（通知 guardian 正常关闭）"""
    if not is_daemon_alive():
        _cleanup_all()
        return True, '守护进程未运行'

    # 先标记 daemon.json 为主动关闭，guardian 看到后会自己退出
    status = read_daemon_status()
    server_pid = status.get('pid')
    guardian_pid = _read_guardian_pid()

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

        # guardian 检测到 stopped 后会自动退出，补一刀确保清理
        if guardian_pid:
            try:
                os.kill(guardian_pid, signal.SIGTERM)
                time.sleep(2)
            except Exception:
                pass
            try:
                os.kill(guardian_pid, 0)
                subprocess.run(['taskkill', '/F', '/PID', str(guardian_pid)],
                               capture_output=True, timeout=5, check=False)
            except (OSError, PermissionError):
                pass

        _cleanup_all()
        return True, '守护进程已停止'
    except Exception as e:
        return False, f'停止失败: {e}'


def restart_daemon():
    """重启守护进程"""
    ok, msg = stop_daemon()
    time.sleep(1)
    return start_daemon()


def _cleanup_all():
    for path_fn in [_daemon_json_path, _guardian_json_path]:
        f = path_fn()
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass
