"""loguru sink — TUI 日志缓冲区（事件驱动，零轮询）"""

import threading
from collections import deque

LOG_BUFFER: deque = deque(maxlen=100)
LOG_EVENT = threading.Event()


class TUILogHandler:
    """loguru sink — 将日志写入缓冲区并通知 TUI"""

    def write(self, message: str) -> None:
        if message.strip():
            LOG_BUFFER.append(message.strip())
            LOG_EVENT.set()
