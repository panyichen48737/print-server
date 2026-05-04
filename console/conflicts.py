import os
import socket
import ctypes
import subprocess
import time
import logging
from pathlib import Path

PID_FILE = None  # lazy init

def _get_pid_file():
    global PID_FILE
    if PID_FILE is None:
        from app._paths import app_root
        PID_FILE = Path(app_root()) / 'logs' / 'console.pid'
    return PID_FILE


def get_local_ips():
    """获取本机所有非回环 IP 地址，IPv4 优先"""
    ips = []
    hostname = socket.gethostname()
    try:
        for addrs in socket.getaddrinfo(hostname, None):
            ip = addrs[4][0]
            if ip.startswith('127.') or ip == '::1':
                continue
            if ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        pass
    if not ips:
        try:
            import psutil
            for _, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                        ips.append(addr.address)
        except ImportError:
            pass
    # IPv4 优先排列
    v4 = [ip for ip in ips if '.' in ip]
    v6 = [ip for ip in ips if ':' in ip]
    return v4 + v6


def check_port_available(port):
    """检测端口是否可用"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result != 0
    except Exception:
        return True


def write_pid():
    """写入当前进程 PID 到文件"""
    pf = _get_pid_file()
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(str(os.getpid()))


def cleanup_pid():
    """删除 PID 文件"""
    try:
        pf = _get_pid_file()
        if pf.exists():
            pf.unlink()
    except Exception:
        pass


def check_conflicts(config, logger):
    """启动前冲突检测，返回 True 可继续"""
    port = config.get('port', 5000)

    stale_pid = False
    old_pid = None
    pf = _get_pid_file()
    if pf.exists():
        try:
            old_pid = int(pf.read_text().strip())
            PROCESS_QUERY_INFORMATION = 0x0400
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, old_pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                logger.warning(f'发现旧控制台进程 (PID: {old_pid}) 仍然存活')
                stale_pid = True
            else:
                cleanup_pid()
        except (ValueError, OSError):
            cleanup_pid()

    if not check_port_available(port):
        logger.error(f'端口 {port} 已被占用')
        if stale_pid:
            logger.error('检测到旧控制台进程残留（窗口关闭但进程未退出）')
            answer = input('\n是否自动终止旧进程？(Y/n): ').strip().lower()
            if answer in ('', 'y', 'yes'):
                try:
                    subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], capture_output=True)
                    time.sleep(1)
                    if check_port_available(port):
                        logger.info('已终止旧进程，端口已释放')
                        cleanup_pid()
                        return True
                except Exception as e:
                    logger.error(f'终止旧进程失败: {e}')
        logger.error('请手动结束残留进程或更改端口')
        return False

    if stale_pid:
        logger.warning('终止无窗口旧控制台进程...')
        try:
            subprocess.run(['taskkill', '/F', '/PID', str(old_pid)], capture_output=True)
        except Exception:
            pass
        cleanup_pid()

    return True
