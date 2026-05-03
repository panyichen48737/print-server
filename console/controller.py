import threading
import logging
import subprocess
import os
import sys

logger = logging.getLogger('print_server')


class ServerState:
    STOPPED = 0
    RUNNING = 1
    CRASHED = 2


def get_autostart_key():
    try:
        result = subprocess.run(
            ['reg', 'query', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
             '/v', 'iOSPrintConsole'],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False


def install_autostart():
    exe_path = os.path.abspath(sys.argv[0])
    if not exe_path.endswith('.exe'):
        exe_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'console_app.py')
        exe_path = os.path.abspath(exe_path)
        launcher = os.path.join(os.path.dirname(exe_path), 'run_console.bat')
        if os.path.exists(launcher):
            exe_path = launcher
    try:
        subprocess.run(
            ['reg', 'add', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
             '/v', 'iOSPrintConsole', '/t', 'REG_SZ', '/d', exe_path, '/f'],
            capture_output=True, text=True, check=True
        )
        return True
    except:
        return False


def uninstall_autostart():
    try:
        subprocess.run(
            ['reg', 'delete', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run',
             '/v', 'iOSPrintConsole', '/f'],
            capture_output=True, text=True, check=True
        )
        return True
    except:
        return False


class ServerController:
    """控制 workers + HTTP 的统一生命周期（eventlet + SocketIO）"""

    def __init__(self, config, app, queue_mgr, print_engine, printer_monitor=None):
        self.config = config
        self.app = app
        self.queue_mgr = queue_mgr
        self.print_engine = print_engine
        self.printer_monitor = printer_monitor
        self._state = ServerState.STOPPED
        self._port = config.get('port', 5000)
        self._srv_thread = None

    @property
    def status(self):
        return self._state

    @property
    def stats(self):
        return self.queue_mgr.get_stats() if self.queue_mgr else {}

    @property
    def port(self):
        return self._port

    def start(self):
        """启动 workers + 打印机监控 + SocketIO 服务器"""
        if self._state == ServerState.RUNNING:
            return
        try:
            self.queue_mgr.start_workers(self.print_engine)
            if self.printer_monitor:
                self.printer_monitor.start()

            from app import socketio
            self._state = ServerState.RUNNING
            self._srv_thread = threading.Thread(
                target=self._run_socketio, args=(socketio,), daemon=True
            )
            self._srv_thread.start()
            logger.info(f'打印服务已启动 (端口: {self._port})')
        except Exception as e:
            logger.error(f'启动失败: {e}')

    def _run_socketio(self, socketio):
        """在后台线程运行 eventlet + SocketIO（只 patch 当前线程所需模块）"""
        import eventlet
        eventlet.monkey_patch(socket=True, select=True, thread=False, os=False, time=True)
        try:
            socketio.run(self.app, host='0.0.0.0', port=self._port, debug=False)
        except Exception as e:
            self._state = ServerState.CRASHED
            logger.error(f'HTTP 服务异常退出: {e}')

    def stop(self):
        """停止服务"""
        if self._state != ServerState.RUNNING:
            return
        try:
            if self.printer_monitor:
                self.printer_monitor.stop()
            self.queue_mgr.stop_workers()
            self._state = ServerState.STOPPED
            self._srv_thread = None
            logger.info('打印服务已停止')
        except Exception as e:
            logger.error(f'停止失败: {e}')

    def restart(self):
        """崩溃后完全重启"""
        self.queue_mgr.stop_workers()
        if self.printer_monitor:
            self.printer_monitor.stop()
        logger.info('2 秒后自动重启打印服务...')
        threading.Event().wait(2)
        self.start()

    def reload_config(self):
        try:
            self.config.load()
            logger.info('配置已重载')
        except Exception as e:
            logger.error(f'重载配置失败: {e}')
