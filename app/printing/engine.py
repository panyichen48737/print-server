"""打印引擎 — 根据文件类型委托给对应的后端策略"""
import threading
from typing import Any, Optional

from loguru import logger

from app.printing.backends import OfficeBackend, PdfBackend, ImageBackend


class PrintEngine:
    """打印调度层，按文件类型分发到不同的 PrinterBackend"""

    def __init__(self, config: Any, dingtalk: Any = None,
                 excel_lock: Optional[threading.Lock] = None,
                 ppt_lock: Optional[threading.Lock] = None) -> None:
        self.config = config
        self.dingtalk = dingtalk

        # 注册后端
        self._backends: dict[str, tuple[str, Any]] = {
            '.doc':  ('office', OfficeBackend(config, excel_lock, ppt_lock)),
            '.docx': ('office', OfficeBackend(config, excel_lock, ppt_lock)),
            '.xls':  ('office', OfficeBackend(config, excel_lock, ppt_lock)),
            '.xlsx': ('office', OfficeBackend(config, excel_lock, ppt_lock)),
            '.ppt':  ('office', OfficeBackend(config, excel_lock, ppt_lock)),
            '.pptx': ('office', OfficeBackend(config, excel_lock, ppt_lock)),
            '.pdf':  ('pdf', PdfBackend(config)),
            '.jpg':  ('image', ImageBackend(config)),
            '.jpeg': ('image', ImageBackend(config)),
            '.png':  ('image', ImageBackend(config)),
            '.bmp':  ('image', ImageBackend(config)),
            '.gif':  ('image', ImageBackend(config)),
            '.webp': ('image', ImageBackend(config)),
            '.tiff': ('image', ImageBackend(config)),
            '.tif':  ('image', ImageBackend(config)),
            '.heic': ('image', ImageBackend(config)),
            '.heif': ('image', ImageBackend(config)),
        }

        self._word_lock = threading.Lock()
        self._excel_lock = excel_lock or threading.Lock()
        self._ppt_lock = ppt_lock or threading.Lock()
        self._active_jobs: dict[str, dict[str, Any]] = {}
        self._active_jobs_lock = threading.Lock()

    def _get_backend(self, file_type: str) -> tuple[str, Any]:
        """查找匹配的后端"""
        ext = file_type.lower()
        entry = self._backends.get(ext)
        if not entry:
            raise ValueError(f'不支持的文件类型: {ext}')
        return entry  # (name, backend_instance)

    def print_file(self, filepath: str, file_type: str, job_id: str,
                   word_lock: Optional[threading.Lock],
                   print_params: Optional[dict[str, Any]] = None) -> Any:
        """根据文件类型分发到对应后端"""
        if print_params is None:
            print_params = {}
        backend_name, backend = self._get_backend(file_type)

        lock = word_lock if backend_name == 'office' else None
        params = dict(print_params)
        params['_file_type'] = file_type

        # 注册到活跃任务
        with self._active_jobs_lock:
            self._active_jobs[job_id] = {'backend_name': backend_name, 'backend': backend}

        try:
            return backend.print_file(filepath, job_id, params, lock=lock)
        finally:
            with self._active_jobs_lock:
                self._active_jobs.pop(job_id, None)

    def cancel_active_job(self, job_id: str) -> bool:
        """取消正在打印的任务，委托给对应后端"""
        with self._active_jobs_lock:
            info = self._active_jobs.get(job_id)
            if not info:
                return False
            backend = info['backend']
            backend_info = dict(info)
            del self._active_jobs[job_id]

        return backend.cancel(job_id, backend_info)
