from collections import deque

LOG_BUFFER: deque = deque(maxlen=100)


class TUILogHandler:
    """loguru sink — TUI 日志缓冲区"""

    def write(self, message: str) -> None:
        if message.strip():
            LOG_BUFFER.append(message.strip())
