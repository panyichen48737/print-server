"""守护进程管理 — 通过子进程启动/停止/监控后台服务器

使用子进程模式管理守护进程（启动文件夹开机自启），不依赖 Windows Service。
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger

DAEMON_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'server_daemon.py'
)


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
    """Windows API 检查进程是否存在"""
    import ctypes

    kernel32 = ctypes.windll.kernel32  # type: ignore
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def _cleanup_stale_daemon() -> None:
    """检测并清理残留的守护进程"""
    status = read_daemon_status()
    pid = status.get('pid')

    if pid and not _win_process_exists(pid):
        logger.warning(f'检测到残留 PID {pid}，清理状态文件')
        _cleanup_json()
        return

    if pid and _win_process_exists(pid) and not _http_healthy(timeout=2):
        logger.warning(f'检测到僵尸进程 PID {pid}，强制终止')
        with contextlib.suppress(Exception):
            subprocess.run(
                ['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=5, check=False
            )
        _cleanup_json()

    if status.get('status') in ('crashed', 'stopped'):
        _cleanup_json()


def is_daemon_alive() -> bool:
    """检查守护进程是否存活 — HTTP 健康检查优先，回退 PID 检查"""
    if _http_healthy(timeout=2):
        return True
    status = read_daemon_status()
    pid = status.get('pid')
    if not pid or status.get('status') != 'running':
        return False
    try:
        return _win_process_exists(pid)
    except (OSError, PermissionError):
        return False


def _http_healthy(timeout: int = 3) -> bool:
    """HTTP/HTTPS 健康检查 — 自动识别协议"""
    status = read_daemon_status()
    port = status.get('port', 5000)
    for proto in ('http', 'https'):
        try:
            import ssl
            import urllib.request

            req = urllib.request.Request(
                f'{proto}://127.0.0.1:{port}/api/health',
                method='GET',
                headers={'Connection': 'close'},
            )
            ctx = None
            if proto == 'https':
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            urllib.request.urlopen(req, timeout=timeout, context=ctx)
            return True
        except Exception:
            continue
    return False


def start_daemon() -> tuple[bool, str]:
    """启动守护进程子进程"""
    if is_daemon_alive():
        return True, '守护进程已在运行'

    _cleanup_stale_daemon()

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

        create_new_process_group = 0x00000200
        detached_process = 0x00000008
        flags = detached_process | create_new_process_group

        stdout_file = open(log_dir / 'daemon_stdout.log', 'a', encoding='utf-8')  # noqa: SIM115
        stderr_file = open(log_dir / 'daemon_stderr.log', 'a', encoding='utf-8')  # noqa: SIM115
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            creationflags=flags,
            stdout=stdout_file,
            stderr=stderr_file,
        )
        stdout_file.close()
        stderr_file.close()
        for _ in range(30):
            if is_daemon_alive():
                return True, f'守护进程已启动 (PID: {proc.pid})'
            time.sleep(1)
        return False, '守护进程启动超时 (30s)'
    except Exception as e:
        return False, f'启动失败: {e}'


def stop_daemon() -> tuple[bool, str]:
    """停止守护进程"""
    if not is_daemon_alive():
        _cleanup_json()
        return True, '守护进程未运行'

    status = read_daemon_status()
    server_pid = status.get('pid')

    try:
        f_daemon = _daemon_json_path()
        with contextlib.suppress(Exception):
            f_daemon.write_text(
                json.dumps({'status': 'stopped', 'pid': server_pid}, ensure_ascii=False)
            )

        if server_pid:
            try:
                os.kill(server_pid, signal.CTRL_BREAK_EVENT)  # type: ignore
                time.sleep(3)
            except Exception:
                pass
            try:
                if _win_process_exists(server_pid):
                    subprocess.run(
                        ['taskkill', '/F', '/PID', str(server_pid)],
                        capture_output=True,
                        timeout=5,
                        check=False,
                    )
            except (OSError, PermissionError):
                pass

        _cleanup_json()
        return True, '守护进程已停止'
    except Exception as e:
        return False, f'停止失败: {e}'


def restart_daemon() -> tuple[bool, str]:
    """重启守护进程"""
    _, _ = stop_daemon()
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
