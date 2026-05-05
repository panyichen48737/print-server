from typing import Any

import httpx
from loguru import logger

from app.services.notifier import Notifier, format_error_message

# 共享长连接客户端
_client = httpx.Client(timeout=10)


class BarkNotifier(Notifier):
    def __init__(self, config: Any) -> None:
        self.config = config

    def send_notification(self, title: str, message: str, _level: str = 'info') -> None:
        if self.config.get('notify_channel', 'disabled') != 'bark':
            return
        key = self.config.get('bark_key', '')
        if not key:
            return
        server = self.config.get('bark_server', 'https://api.day.app')
        try:
            payload = {'title': title, 'body': message, 'group': 'PrintServer'}
            resp = _client.post(f'{server}/{key}', json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info('Bark 通知发送成功')
            else:
                logger.warning(f'Bark 通知发送失败: {resp.status_code}')
        except Exception as e:
            logger.warning(f'Bark 通知异常: {e}')

    def notify_job_completed(self, filename: str, time_str: str) -> None:
        self.send_notification('打印任务完成', f'文件: {filename}\n时间: {time_str}')

    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None:
        friendly = format_error_message(error)
        self.send_notification(
            '打印任务失败', f'文件: {filename}\n原因: {friendly}\n时间: {time_str}'
        )
