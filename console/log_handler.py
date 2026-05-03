import logging

LOG_BUFFER = []


class TUILogHandler(logging.Handler):
    """将日志重定向到 TUI 面板的处理器"""

    def __init__(self, max_lines=100):
        super().__init__()
        self.max_lines = max_lines

    def emit(self, record):
        msg = self.format(record)
        LOG_BUFFER.append(msg)
        if len(LOG_BUFFER) > self.max_lines:
            LOG_BUFFER[:] = LOG_BUFFER[-self.max_lines:]
