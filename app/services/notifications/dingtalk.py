from typing import Any

from loguru import logger

from app.services.notifications import HttpNotifier, Notifier, format_error_message


class DingTalk(Notifier, HttpNotifier):
    def __init__(self, config: Any, client=None) -> None:
        self.config = config
        HttpNotifier.__init__(self, client)

    def send_notification(self, title: str, message: str, level: str = 'error') -> None:
        webhook = self.config.get('dingtalk_webhook', '')
        if not webhook:
            return

        notify_level = self.config.get('dingtalk_level', 'error')
        if notify_level == 'error' and level != 'error':
            return

        content = f'{title}\n\n{message}'
        payload = {'msgtype': 'text', 'text': {'content': content}}
        ok = self._post(webhook, payload)
        if ok:
            logger.info('钉钉通知发送成功')
        else:
            logger.warning('钉钉通知发送失败')

    def notify_job_completed(self, filename: str, time_str: str) -> None:
        self.send_notification('打印任务完成', f'文件: {filename}\n时间: {time_str}', level='info')

    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None:
        friendly = format_error_message(error)
        self.send_notification(
            '打印任务失败', f'文件: {filename}\n原因: {friendly}\n时间: {time_str}', level='error'
        )
