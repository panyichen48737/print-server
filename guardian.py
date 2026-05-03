"""守护进程看门狗 — 启动并监控 server_daemon.py，定时健康检查 + 崩溃自动重启"""
import os
import sys
import json
import time
import ssl
import subprocess
import urllib.request
import atexit
from pathlib import Path


DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server_daemon.py')
CHECK_INTERVAL = 15
MAX_HTTP_FAIL = 3


def _config_port():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')) as f:
            return json.load(f).get('port', 5000)
    except Exception:
        return 5000


def _status_path():
    from app._paths import app_root
    return Path(app_root()) / 'logs' / 'guardian.json'


def write_guardian_pid(pid):
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
    from app._paths import app_root
    f = Path(app_root()) / 'logs' / 'daemon.json'
    if not f.exists():
        return {'status': 'stopped'}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {'status': 'stopped'}


def write_daemon_status(status, **extra):
    from app._paths import app_root
    f = Path(app_root()) / 'logs' / 'daemon.json'
    try:
        data = {'status': status, **extra}
        f.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


def http_health_check(port):
    """健康检查 — 先试 HTTP，失败则试 HTTPS"""
    for proto in ('http', 'https'):
        try:
            ctx = None
            if proto == 'https':
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(f'{proto}://127.0.0.1:{port}/api/printers/status',
                                         method='GET', headers={'Connection': 'close'})
            urllib.request.urlopen(req, timeout=5, context=ctx)
            return True
        except Exception:
            continue
    return False


def log(msg, log_dir):
    try:
        with open(log_dir / 'daemon_stdout.log', 'a') as f:
            f.write(f'[guardian] {msg}\n')
    except Exception:
        pass


def _server_cmd():
    """返回启动 server_daemon 的命令"""
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--server-daemon']
    return [sys.executable, DAEMON_SCRIPT]


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    write_guardian_pid(os.getpid())
    atexit.register(cleanup_guardian_pid)

    from app._paths import app_root
    log_dir = Path(app_root()) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    restart_count = 0
    max_restarts = 10
    port = _config_port()
    http_fail_count = 0

    while restart_count < max_restarts:
        stdout_f = open(log_dir / 'daemon_stdout.log', 'a')
        stderr_f = open(log_dir / 'daemon_stderr.log', 'a')

        CREATE_NO_WINDOW = 0x08000000
        proc = subprocess.Popen(
            _server_cmd(),
            cwd=os.path.dirname(DAEMON_SCRIPT),
            creationflags=CREATE_NO_WINDOW,
            stdout=stdout_f,
            stderr=stderr_f,
        )

        daemon_pid = proc.pid
        log(f'守护进程已启动 (PID: {daemon_pid})', log_dir)
        http_fail_count = 0

        while True:
            check_interval = 5 if http_fail_count > 0 else CHECK_INTERVAL
            time.sleep(check_interval)

            ret = proc.poll()
            if ret is not None:
                log(f'守护进程已退出 (PID: {daemon_pid}, 返回码: {ret})', log_dir)
                break

            if http_health_check(port):
                http_fail_count = 0
            else:
                http_fail_count += 1
                if http_fail_count >= MAX_HTTP_FAIL:
                    log(f'健康检查连续失败 {MAX_HTTP_FAIL} 次，终止进程', log_dir)
                    # 提前写 daemon.json 防止误判崩溃（M1）
                    write_daemon_status('stopped', pid=daemon_pid)
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except Exception:
                        subprocess.run(['taskkill', '/F', '/PID', str(daemon_pid)],
                                       capture_output=True)
                    break

        stdout_f.close()
        stderr_f.close()

        status = read_daemon_status()
        is_intentional = status.get('status') == 'stopped'

        if is_intentional:
            log('守护进程正常关闭，退出监控', log_dir)
            break

        restart_count += 1
        log(f'守护进程异常退出，第 {restart_count}/{max_restarts} 次重启', log_dir)

        if restart_count >= max_restarts:
            log(f'达到最大重启次数 ({max_restarts})，停止监控', log_dir)
            break

        time.sleep(5)

    cleanup_guardian_pid()


if __name__ == '__main__':
    main()
