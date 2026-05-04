"""打印服务层：编排打印任务生命周期，路由通过此类调用而非直接操作 QueueManager"""
from datetime import datetime
from typing import Any

from loguru import logger

from app.upload_helper import UploadResult, handle_file_upload


class PrintService:
    def __init__(
        self,
        config: Any,
        queue_manager: Any,
        event_bus: Any = None,
        notifier: Any = None,
    ) -> None:
        self._config = config
        self._queue_manager = queue_manager
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
            filename, content, self._config, self._queue_manager,
            source=source, **print_options
        )

    def cancel_job(self, job_id: str) -> Any:
        return self._queue_manager.cancel_job(job_id)

    def cancel_all_queued(self) -> Any:
        return self._queue_manager.cancel_all_queued()

    def retry_job(self, job_id: str) -> Any:
        return self._queue_manager.retry_job(job_id)

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
        time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
