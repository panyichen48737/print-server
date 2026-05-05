"""守护进程管理 — 通过子进程启动/停止/监控后台服务器

策略：
  如果 Windows Service 已注册 → start/stop 操作服务
  否则 → 管理守护进程子进程（兼容启动文件夹模式）
"""
import os
import sys
import json
import time
import signal
import subprocess
from pathlib import Path

from loguru import logger


DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'server_daemon.py')
SERVICE_NAME = 'iOSPrintServer'


def _daemon_json_path() -> Path:
    from app._paths import persistent_dir
    return Path(persistent_dir()) / 'logs' / 'daemon.json'


def read_daemon_status() -> dict:
    """读取守护进程状态 JSON"""
    f = _daemon_json_path()
    if not f.exists():
        return {'status': 'stopped', 'pid': None}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {'status': 'stopped', 'pid': None}


def _win_process_exists(pid: int) -> bool:
    """Windows API 检查进程是否存在（比 os.kill(pid,0) 更可靠）"""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def _service_installed() -> bool:
    """检查 Windows Service 是否已注册"""
    try:
        r = subprocess.run(
            ['sc', 'query', SERVICE_NAME],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and 'STATE' in r.stdout
    except Exception:
        return False


def _service_running() -> bool:
    """检查 Windows Service 是否正在运行"""
    try:
        r = subprocess.run(
            ['sc', 'query', SERVICE_NAME],
            capture_output=True, text=True, timeout=5,
        )
        return 'STATE' in r.stdout and 'RUNNING' in r.stdout
    except Exception:
        return False


def is_daemon_alive() -> bool:
    """检查守护进程是否存活

    优先 HTTP 健康检查（最准确），回退 PID 检查。
    服务模式下 server_daemon.py 未注册 SCM 回调，sc query 不可靠。
    """
    # HTTP 健康检查是最终权威判断
    if _http_healthy(timeout=2):
        return True
    # 回退：检查 daemon.json 中的 PID
    status = read_daemon_status()
    pid = status.get('pid')
    if not pid or status.get('status') != 'running':
        return False
    try:
        return _win_process_exists(pid)
    except (OSError, PermissionError):
        return False


def _http_healthy(timeout: int = 3) -> bool:
    """HTTP 健康检查 — 确认服务器实际在响应请求"""
    status = read_daemon_status()
    port = status.get('port', 5000)
    try:
        import urllib.request
        req = urllib.request.Request(
            f'http://127.0.0.1:{port}/api/health',
            method='GET',
            headers={'Connection': 'close'},
        )
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def start_daemon() -> tuple[bool, str]:
    """启动守护进程（服务优先，回退子进程）"""
    if is_daemon_alive():
        return True, '守护进程已在运行'

    # 1. 尝试 Windows Service
    if _service_installed():
        try:
            subprocess.run(['sc', 'start', SERVICE_NAME],
                           capture_output=True, timeout=30)
            # server_daemon.py 未注册 SCM 回调，sc query 不会显示 RUNNING，
            # 因此直接用 HTTP 健康检查判断服务是否就绪
            for _ in range(30):
                if _http_healthy():
                    return True, 'Windows 服务已启动'
                time.sleep(1)
            return False, 'Windows 服务启动超时 (30s)'
        except Exception as e:
            return False, f'服务启动失败: {e}'

    # 2. 回退子进程模式
    from app._paths import persistent_dir
    log_dir = Path(persistent_dir()) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    try:
        if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False):
            cmd = [sys.executable, '--server-daemon']
            cwd = os.path.dirname(sys.executable)
        else:
            cmd = [sys.executable, DAEMON_SCRIPT]
            cwd = os.path.dirname(os.path.dirname(DAEMON_SCRIPT))

        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            creationflags=flags,
            stdout=open(log_dir / 'daemon_stdout.log', 'a', encoding='utf-8'),
            stderr=open(log_dir / 'daemon_stderr.log', 'a', encoding='utf-8'),
        )
        for _ in range(30):
            if is_daemon_alive():
                return True, f'守护进程已启动 (PID: {proc.pid})'
            time.sleep(1)
        return False, '守护进程启动超时 (30s)'
    except Exception as e:
        return False, f'启动失败: {e}'


def stop_daemon() -> tuple[bool, str]:
    """停止守护进程（服务优先，回退子进程）"""
    # 1. 尝试 Windows Service
    if _service_installed():
        try:
            subprocess.run(['sc', 'stop', SERVICE_NAME],
                           capture_output=True, timeout=15)
            for _ in range(6):
                if not _service_running():
                    _cleanup_json()
                    return True, 'Windows 服务已停止'
                time.sleep(1)
            return False, 'Windows 服务停止超时'
        except Exception as e:
            return False, f'服务停止失败: {e}'

    # 2. 回退子进程模式
    if not is_daemon_alive():
        _cleanup_json()
        return True, '守护进程未运行'

    status = read_daemon_status()
    server_pid = status.get('pid')

    try:
        f_daemon = _daemon_json_path()
        try:
            f_daemon.write_text(json.dumps({'status': 'stopped', 'pid': server_pid}, ensure_ascii=False))
        except Exception:
            pass

        if server_pid:
            try:
                os.kill(server_pid, signal.CTRL_BREAK_EVENT)
                time.sleep(3)
            except Exception:
                pass
            try:
                if _win_process_exists(server_pid):
                    subprocess.run(['taskkill', '/F', '/PID', str(server_pid)],
                                   capture_output=True, timeout=5, check=False)
            except (OSError, PermissionError):
                pass

        _cleanup_json()
        return True, '守护进程已停止'
    except Exception as e:
        return False, f'停止失败: {e}'


def restart_daemon() -> tuple[bool, str]:
    """重启守护进程"""
    ok, msg = stop_daemon()
    time.sleep(1)
    return start_daemon()


def _cleanup_json() -> None:
    for path_fn in [_daemon_json_path]:
        f = path_fn()
        try:
            if f.exists():
                f.unlink()
        except Exception:
            pass
