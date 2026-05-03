import threading
import logging
from datetime import datetime

logger = logging.getLogger('print_server')


class ServerState:
    STOPPED = 0
    RUNNING = 1
    CRASHED = 2


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
