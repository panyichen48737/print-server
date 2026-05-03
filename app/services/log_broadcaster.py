"""通过 SSE 广播器实时推送日志行"""
import logging
from app.services.sse_broadcaster import get_broadcaster

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class LogBroadcaster(logging.Handler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    def emit(self, record):
        try:
            msg = self.format(record)
            get_broadcaster().publish('log', {
                'message': msg,
                'level': record.levelname,
                'name': record.name,
            })
        except Exception:
            pass
