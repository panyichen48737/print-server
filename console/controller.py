import threading
import logging
import subprocess
import os
import sys
from datetime import datetime

logger = logging.getLogger('print_server')


class ServerState:
    STOPPED = 0
    RUNNING = 1
    CRASHED = 2


def get_autostart_key():
    """检查 HKCU\Run 是否已注册自启"""
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
    """注册当前 exe 到开机自启"""
    exe_path = os.path.abspath(sys.argv[0])
    if not exe_path.endswith('.exe'):
        # 开发模式，注册控制台入口
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
    """删除开机自启注册"""
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
    """控制 workers + HTTP 的统一生命周期"""

    def __init__(self, config, app, queue_mgr, print_engine):
        self.config = config
        self.app = app
        self.queue_mgr = queue_mgr
        self.print_engine = print_engine
        self._state = ServerState.STOPPED
        self.httpd = None
        self._port = config.get('port', 5000)

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
        """启动 workers + HTTP"""
        if self._state == ServerState.RUNNING:
            return
        try:
            self.queue_mgr.start_workers(self.print_engine)

            from waitress import create_server
            self.httpd = create_server(
                self.app, host='0.0.0.0', port=self._port,
                connection_limit=1000, cleanup_interval=30,
            )
            self._state = ServerState.RUNNING
            t = threading.Thread(target=self._server_runner, daemon=True)
            t.start()
            logger.info(f'打印服务已启动 (端口: {self._port})')
        except Exception as e:
            logger.error(f'启动失败: {e}')

    def stop(self):
        """停止 HTTP + workers"""
        if self._state != ServerState.RUNNING or not self.httpd:
            return
        try:
            self.httpd.close()
            self.httpd = None
            self.queue_mgr.stop_workers()
            self._state = ServerState.STOPPED
            logger.info('打印服务已停止')
        except Exception as e:
            logger.error(f'停止失败: {e}')

    def restart(self):
        """崩溃后完全重启（先 stop 再 start）"""
        if self.httpd:
            try:
                self.httpd.close()
            except Exception:
                pass
            self.httpd = None
        self.queue_mgr.stop_workers()
        logger.info('2 秒后自动重启打印服务...')
        threading.Event().wait(2)
        self.start()

    def reload_config(self):
        """热加载配置"""
        try:
            self.config.load()
            logger.info('配置已重载')
        except Exception as e:
            logger.error(f'重载配置失败: {e}')

    def _server_runner(self):
        """在后台线程运行 waitress"""
        try:
            self.httpd.run()
        except Exception as e:
            self._state = ServerState.CRASHED
            logger.error(f'HTTP 服务异常退出: {e}')
