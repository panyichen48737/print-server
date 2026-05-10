from typing import Any

from loguru import logger

from app.services.notifications import HttpNotifier, Notifier, format_error_message


class BarkNotifier(Notifier, HttpNotifier):
    def __init__(self, config: Any, client=None) -> None:
        self.config = config
        HttpNotifier.__init__(self, client)

    def send_notification(self, title: str, message: str, _level: str = 'info') -> None:
        if self.config.get('notify_channel', 'disabled') != 'bark':
            return
        key = self.config.get('bark_key', '')
        if not key:
            return
        server = self.config.get('bark_server', 'https://api.day.app')
        payload = {'title': title, 'body': message, 'group': 'PrintServer'}
        ok = self._post(f'{server}/{key}', payload)
        if ok:
            logger.info('Bark 通知发送成功')
        else:
            logger.warning('Bark 通知发送失败')

    def notify_job_completed(self, filename: str, time_str: str) -> None:
        self.send_notification('打印任务完成', f'文件: {filename}\n时间: {time_str}')

    def notify_job_failed(self, filename: str, error: str, time_str: str) -> None:
        friendly = format_error_message(error)
        self.send_notification(
            '打印任务失败', f'文件: {filename}\n原因: {friendly}\n时间: {time_str}'
        )
