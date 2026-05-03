"""iOS 云打印服务器 — 控制台捆绑体（管理后台守护进程）

用法:
    python -m console         启动控制台（自动启动后台服务）
    python -m console --start 仅启动后台服务（无界面）
    python -m console --stop  停止后台服务
    python -m console --status 查看后台服务状态
"""
import sys
import os
import logging
import argparse

from app._paths import app_root

sys.path.insert(0, app_root())

from app.config import Config, setup_logging
from .log_handler import LOG_BUFFER, TUILogHandler
from .daemon_manager import start_daemon, stop_daemon, read_daemon_status, is_daemon_alive, restart_daemon
from .autostart import install_autostart, uninstall_autostart, is_autostart_installed
from .tui import TUI


def main():
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
        logger = setup_logging(level=config.log_level)
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
        print(f'状态: {"● 运行中" if alive else "○ 已停止"}')
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

    # 默认：启动控制台 TUI
    config = Config()
    logger = setup_logging(level=config.log_level)

    tui_handler = TUILogHandler()
    tui_handler.setFormatter(
        logging.Formatter('%(asctime)s  %(levelname)s  %(message)s', datefmt='%H:%M:%S')
    )
    logging.getLogger('print_server').addHandler(tui_handler)

    # 自动启动后台守护进程
    ok, msg = start_daemon()
    logger.info(msg)

    # 首次启动自动注册开机自启
    if not is_autostart_installed():
        ok2, msg2 = install_autostart()
        logger.info(msg2)

    try:
        TUI().run()
    except KeyboardInterrupt:
        pass

    # 退出控制台时询问是否保持后台运行
    if is_daemon_alive():
        print('\n后台服务仍在运行，可通过以下方式管理:')
        print('  python -m console --status    查看状态')
        print('  python -m console --stop      停止服务')
        print('  python -m console --start     启动服务')
        print('  或重新打开控制台管理')


if __name__ == '__main__':
    main()
