"""打印服务层：编排打印任务生命周期"""
from typing import Any

from loguru import logger

from app.upload_helper import UploadResult, handle_file_upload
from app.utils import format_time


class PrintService:
    def __init__(
        self,
        config: Any,
        job_queue: Any,
        event_bus: Any = None,
        notifier: Any = None,
    ) -> None:
        self._config = config
        self._job_queue = job_queue
        self._event_bus = event_bus
        self._notifier = notifier

    def submit_print(
        self,
        filename: str,
        content: bytes,
        source: str = 'api',
        **print_options: Any,
    ) -> UploadResult:
        """校验文件、保存、入队，委托给 upload_helper"""
        return handle_file_upload(
            filename, content, self._config, self._job_queue,
            source=source, **print_options
        )

    def set_default_printer(self, printer_name: str) -> None:
        self._config.set('default_printer', printer_name)
        self._config.save()
        logger.info(f'默认打印机已设置: {printer_name}')

    def test_notification(
        self,
        channel: str,
        dingtalk_instance: Any,
        bark_instance: Any,
    ) -> None:
        """发送测试通知"""
        time_str = format_time()
        if channel == 'dingtalk' and dingtalk_instance:
            dingtalk_instance.send_notification(
                '测试通知',
                f'这是一条测试消息\n时间: {time_str}',
                level='info',
            )
        elif channel == 'bark' and bark_instance:
            bark_instance.send_notification(
                '测试通知',
                f'这是一条测试消息\n时间: {time_str}',
            )
