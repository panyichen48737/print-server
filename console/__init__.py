"""iOS 云打印服务器 — 控制台捆绑体（管理后台守护进程）

用法:
    python -m console         启动控制台（自动启动后台服务）
    python -m console --start 仅启动后台服务（无界面）
    python -m console --stop  停止后台服务
    python -m console --status 查看后台服务状态
"""

import argparse
import sys
import threading

from loguru import logger

from app._paths import app_root

sys.path.insert(0, app_root())

from app.config import Config
from app.logging import setup_logging
from app.self_install import ensure_installed

from .autostart import install_autostart, is_autostart_installed, uninstall_autostart
from .daemon_manager import (
    is_daemon_alive,
    read_daemon_status,
    restart_daemon,
    start_daemon,
    stop_daemon,
)
from .log_handler import TUILogHandler


def _ensure_single_instance() -> None:
    """Windows 命名互斥体：防止启动多个控制台窗口"""
    import ctypes

    mutex = ctypes.windll.kernel32.CreateMutexW(None, True, 'iOSPrintServerConsole')  # type: ignore
    err = ctypes.windll.kernel32.GetLastError()  # type: ignore
    if not mutex:
        print(f'[WARN] 无法创建互斥体 (error={err})，继续启动')
        return
    if err == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.kernel32.CloseHandle(mutex)  # type: ignore
        print('控制台已在运行')
        sys.exit(0)
    # err == 0: 新创建，正常持有；其他异常值记录日志
    if err != 0:
        print(f'[WARN] 互斥体状态异常 (error={err})')


def main() -> int | None:
    # 冻结 EXE 入口：--server-daemon 参数直接路由到服务器入口
    if '--server-daemon' in sys.argv:
        from app.server_daemon import main as daemon_main

        daemon_main()
        sys.exit(0)
        return None
        return

    parser = argparse.ArgumentParser(description='iOS 云打印服务器控制台')
    parser.add_argument('--start', action='store_true', help='启动后台服务（无界面）')
    parser.add_argument('--stop', action='store_true', help='停止后台服务')
    parser.add_argument('--restart', action='store_true', help='重启后台服务')
    parser.add_argument('--status', action='store_true', help='查看后台服务状态')
    parser.add_argument('--autostart-install', action='store_true', help='注册开机自启')
    parser.add_argument('--autostart-uninstall', action='store_true', help='卸载开机自启')
    args = parser.parse_args()

    if args.start:
        config = Config()
        setup_logging(level=config.log_level)
        if not ensure_installed():
            return 0
        ok, msg = start_daemon()
        print(msg)
        return 0 if ok else 1

    if args.stop:
        ok, msg = stop_daemon()
        print(msg)
        return 0 if ok else 1

    if args.restart:
        ok, msg = restart_daemon()
        print(msg)
        return 0 if ok else 1

    if args.status:
        status = read_daemon_status()
        alive = is_daemon_alive()
        print(f'状态: {"运行中" if alive else "已停止"}')
        print(f'PID: {status.get("pid", "-")}')
        print(f'端口: {status.get("port", "-")}')
        print(f'自启: {"已注册" if is_autostart_installed() else "未注册"}')
        return 0

    if args.autostart_install:
        ok, msg = install_autostart()
        print(msg)
        return 0 if ok else 1

    if args.autostart_uninstall:
        ok, msg = uninstall_autostart()
        print(msg)
        return 0 if ok else 1

    # 默认：启动控制台 TUI（只允许一个实例）
    _ensure_single_instance()
    config = Config()
    setup_logging(level=config.log_level)

    if not ensure_installed():
        return None

    tui_handler = TUILogHandler()
    logger.add(tui_handler, format='{time:HH:mm:ss} {level} {message}', level='INFO')

    try:
        # TUI 先启动，界面就绪后再后台启动守护进程
        from .tui import TUI

        app = TUI()
        threading.Thread(target=_start_daemon_background, daemon=True).start()
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback

        error_detail = traceback.format_exc()
        logger.error(f'TUI 启动失败: {e}\n{error_detail}')
        try:
            from pathlib import Path

            from app._paths import persistent_dir

            diag = Path(persistent_dir()) / 'logs' / 'tui_error.log'
            diag.parent.mkdir(parents=True, exist_ok=True)
            diag.write_text(error_detail)
        except Exception:
            pass
        print(f'\nTUI 界面启动失败: {e}')
        print('服务已在后台运行，请访问 Web 管理页面:')
        from .conflicts import get_local_ips

        status = read_daemon_status()
        port = status.get('port', 5000)
        ips = get_local_ips()
        ip_str = ips[0] if ips else '127.0.0.1'
        print(f'  https://{ip_str}:{port}/admin')
        print('\n按 Enter 退出...')
        input()

    return None

    # 退出控制台时询问是否保持后台运行
    if is_daemon_alive():
        print('\n后台服务仍在运行，可通过以下方式管理:')
        print('  python -m console --status    查看状态')
        print('  python -m console --stop      停止服务')
        print('  python -m console --start     启动服务')
        print('  或重新打开控制台管理')


def _start_daemon_background():
    """后台线程：启动守护进程 + 首次自动注册开机自启"""
    ok, msg = start_daemon()
    logger.info(msg)
    if ok and not is_autostart_installed():
        _ok2, msg2 = install_autostart()
        logger.info(msg2)


if __name__ == '__main__':
    main()
