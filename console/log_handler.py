import logging
from collections import deque

LOG_BUFFER = deque(maxlen=100)


class TUILogHandler(logging.Handler):
    """将日志重定向到 TUI 面板的处理器"""

    def __init__(self, max_lines=100):
        super().__init__()
        self.max_lines = max_lines
        global LOG_BUFFER
        LOG_BUFFER = deque(maxlen=max_lines)

    def emit(self, record):
        msg = self.format(record)
        LOG_BUFFER.append(msg)
