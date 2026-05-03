"""iOS 云打印服务器 — 控制台捆绑体

用法:
    python -m console
"""
import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import Config, setup_logging
from app import bootstrap
from .conflicts import check_conflicts, write_pid, cleanup_pid
from .log_handler import LOG_BUFFER, TUILogHandler
from .controller import ServerController, ServerState
from .tui import TUI

_global_ctrl = None


def _console_ctrl_handler(dwCtrlType):
    """捕获控制台关闭事件（点 X），执行优雅关闭后强制退出"""
    if dwCtrlType in (0, 1, 2):
        if _global_ctrl:
            if _global_ctrl.status == ServerState.RUNNING:
                _global_ctrl.stop()
            _global_ctrl.queue_mgr.shutdown()
            cleanup_pid()
        os._exit(0)
    return False


def main():
    config = Config()
    logger = setup_logging(level=config.log_level)

    # TUI 日志处理器
    tui_handler = TUILogHandler()
    tui_handler.setFormatter(
        logging.Formatter('%(asctime)s  %(levelname)s  %(message)s', datefmt='%H:%M:%S')
    )
    logging.getLogger('print_server').addHandler(tui_handler)

    # 初始化服务组件
    app, queue_mgr, print_engine = bootstrap(config)

    # 冲突检测
    if not check_conflicts(config, logger):
        logger.error('检测到冲突，控制台退出')
        input('\n按 Enter 键退出...')
        sys.exit(1)

    write_pid()

    # 控制器
    global _global_ctrl
    ctrl = ServerController(config, app, queue_mgr, print_engine)
    _global_ctrl = ctrl
    try:
        import win32api
        win32api.SetConsoleCtrlHandler(_console_ctrl_handler, True)
    except ImportError:
        pass

    ctrl.start()

    try:
        TUI(ctrl).run()
    finally:
        ctrl.stop()
        cleanup_pid()


if __name__ == '__main__':
    main()
