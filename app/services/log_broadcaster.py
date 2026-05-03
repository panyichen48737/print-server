"""通过 SocketIO 实时推送日志行"""
import logging
from app import socketio

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class LogBroadcaster(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    def emit(self, record):
        try:
            msg = self.format(record)
            socketio.emit('log', {
                'message': msg,
                'level': record.levelname,
                'name': record.name,
            }, namespace='/')
        except Exception:
            pass
