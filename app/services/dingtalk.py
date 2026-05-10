from typing import Any

import httpx
from loguru import logger

from app.services.notifier import Notifier, format_error_message


class DingTalk(Notifier):
    def __init__(self, config: Any, client: httpx.Client | None = None) -> None:
        self.config = config
        self._client = client or httpx.Client(timeout=10)

    def send_notification(self, title: str, message: str, level: str = 'error') -> None:
        """发送钉钉通知"""
        webhook = self.config.get('dingtalk_webhook', '')
        if not webhook:
            return

        notify_level = self.config.get('dingtalk_level', 'error')
        if notify_level == 'error' and level != 'error':
            return

        try:
            content = f'{title}\n\n{message}'
            payload = {'msgtype': 'text', 'text': {'content': content}}
            resp = self._client.post(webhook, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info('钉钉通知发送成功')
            else:
                logger.warning(f'钉钉通知发送失败: {resp.status_code}')
        except Exception as e:
            logger.warning(f'钉钉通知异常: {e}')

    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None:
        """任务失败通知"""
        friendly = format_error_message(error)
        self.send_notification(
            '打印任务失败', f'文件: {filename}\n原因: {friendly}\n时间: {time_str}', level='error'
        )

    def notify_job_completed(self, filename: str, time_str: str) -> None:
        """任务完成通知"""
        self.send_notification('打印任务完成', f'文件: {filename}\n时间: {time_str}', level='info')
