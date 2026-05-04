"""通过 SSE 广播器实时推送日志行"""


class LogBroadcaster:
    """loguru sink — 将日志推送到 SSE"""

    def __init__(self, broadcaster=None):
        self._broadcaster = broadcaster

    def write(self, message):
        if message.strip() and self._broadcaster:
            self._broadcaster.publish('log', {
                'message': message.strip(),
                'level': 'INFO',
                'name': 'print_server',
            })
