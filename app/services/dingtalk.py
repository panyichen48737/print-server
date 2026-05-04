from typing import Any

from loguru import logger
import httpx

from app.services.notifier import Notifier, format_error_message


class DingTalk(Notifier):
    def __init__(self, config: Any) -> None:
        self.config = config

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
            payload = {
                'msgtype': 'text',
                'text': {
                    'content': content
                }
            }
            with httpx.Client() as client:
                resp = client.post(webhook, json=payload, timeout=10)
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
            '打印任务失败',
            f'文件: {filename}\n原因: {friendly}\n时间: {time_str}',
            level='error'
        )

    def notify_job_completed(self, filename: str, time_str: str) -> None:
        """任务完成通知"""
        self.send_notification(
            '打印任务完成',
            f'文件: {filename}\n时间: {time_str}',
            level='info'
        )

    def notify_job_cancelled(self, filename: str, time_str: str) -> None:
        """任务取消通知"""
        self.send_notification(
            '打印已取消',
            f'文件: {filename}\n时间: {time_str}',
            level='warning'
        )
