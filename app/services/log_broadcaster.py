"""通过 SSE 广播器实时推送日志行"""
import logging

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class LogBroadcaster(logging.Handler):
    def __init__(self, broadcaster=None):
        super().__init__()
        self._broadcaster = broadcaster
        self.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    def emit(self, record):
        if not self._broadcaster:
            return
        try:
            msg = self.format(record)
            self._broadcaster.publish('log', {
                'message': msg,
                'level': record.levelname,
                'name': record.name,
            })
        except Exception:
            pass
