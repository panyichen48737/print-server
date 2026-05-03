import logging
import requests

from app.services.notifier import Notifier

logger = logging.getLogger('print_server')


class BarkNotifier(Notifier):
    def __init__(self, config):
        self.config = config

    def send_notification(self, title, message, level='info'):
        if self.config.get('notify_channel', 'disabled') != 'bark':
            return
        key = self.config.get('bark_key', '')
        if not key:
            return
        server = self.config.get('bark_server', 'https://api.day.app')
        try:
            payload = {'title': title, 'body': message, 'group': 'PrintServer'}
            resp = requests.post(f'{server}/{key}', json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info('Bark 通知发送成功')
            else:
                logger.warning(f'Bark 通知发送失败: {resp.status_code}')
        except Exception as e:
            logger.warning(f'Bark 通知异常: {e}')

    def notify_job_completed(self, filename, time_str):
        self.send_notification('✅ 打印任务完成', f'文件: {filename}\n时间: {time_str}')

    def notify_job_failed(self, filename, error, time_str):
        self.send_notification('❌ 打印任务失败', f'文件: {filename}\n错误: {error}\n时间: {time_str}')

    def notify_job_cancelled(self, filename, time_str):
        self.send_notification('⏹ 打印已取消', f'文件: {filename}\n时间: {time_str}')
