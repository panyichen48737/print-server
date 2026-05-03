"""守护进程看门狗 — 启动并监控 server_daemon.py，崩溃时自动重启

工作方式:
  1. guardian 启动 server_daemon.py 作为子进程
  2. 子进程退出时，判断是主动关闭还是崩溃
  3. 崩溃 → 5秒后自动重启
  4. 主动关闭 → guardian 退出
"""
import os
import sys
import json
import time
import subprocess
import atexit
from pathlib import Path

# 确保在项目根目录
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server_daemon.py')


def _status_path():
    from app._paths import app_root
    return Path(app_root()) / 'logs' / 'guardian.json'


def write_guardian_pid(pid):
    """写入 guardian PID"""
    f = _status_path()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({'guardian_pid': pid}, ensure_ascii=False))
    except Exception:
        pass


def cleanup_guardian_pid():
    try:
        f = _status_path()
        if f.exists():
            f.unlink()
    except Exception:
        pass


def read_daemon_status():
    """读取 server_daemon.py 的状态文件"""
    from app._paths import app_root
    f = Path(app_root()) / 'logs' / 'daemon.json'
    if not f.exists():
        return {'status': 'stopped'}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {'status': 'stopped'}


def main():
    write_guardian_pid(os.getpid())
    atexit.register(cleanup_guardian_pid)

    restart_count = 0
    max_restarts = 10  # 防止无限崩溃循环

    while restart_count < max_restarts:
        from app._paths import app_root
        log_dir = Path(app_root()) / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)

        stdout_f = open(log_dir / 'daemon_stdout.log', 'a')
        stderr_f = open(log_dir / 'daemon_stderr.log', 'a')

        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            [sys.executable, DAEMON_SCRIPT],
            cwd=os.path.dirname(DAEMON_SCRIPT),
            creationflags=CREATE_NO_WINDOW,
            stdout=stdout_f,
            stderr=stderr_f,
        )

        daemon_pid = proc.pid
        # 等待退出
        proc.wait()

        stdout_f.close()
        stderr_f.close()

        # 读 daemon.json 判断是主动关闭还是崩溃
        status = read_daemon_status()
        is_intentional = status.get('status') == 'stopped'

        if is_intentional:
            with open(log_dir / 'daemon_stdout.log', 'a') as f:
                f.write(f'[guardian] 守护进程正常退出 (PID: {daemon_pid})\n')
            break

        # 崩溃了，重启
        restart_count += 1
        with open(log_dir / 'daemon_stdout.log', 'a') as f:
            f.write(f'[guardian] 守护进程异常退出 (PID: {daemon_pid}, 第{restart_count}次重启)\n')

        if restart_count >= max_restarts:
            with open(log_dir / 'daemon_stdout.log', 'a') as f:
                f.write(f'[guardian] 达到最大重启次数 ({max_restarts})，停止监控\n')
            break

        time.sleep(3)  # 等待3秒后重启

    cleanup_guardian_pid()


if __name__ == '__main__':
    main()
