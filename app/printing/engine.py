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

        pdf_backend = PdfBackend(config)
        office_backend = OfficeBackend(config, excel_lock, ppt_lock)
        image_backend = ImageBackend(config, pdf_backend)

        self._backends: dict[str, tuple[str, Any]] = {
            '.doc':  ('office', office_backend),
            '.docx': ('office', office_backend),
            '.xls':  ('office', office_backend),
            '.xlsx': ('office', office_backend),
            '.ppt':  ('office', office_backend),
            '.pptx': ('office', office_backend),
            '.pdf':  ('pdf', pdf_backend),
            '.jpg':  ('image', image_backend),
            '.jpeg': ('image', image_backend),
            '.png':  ('image', image_backend),
            '.bmp':  ('image', image_backend),
            '.gif':  ('image', image_backend),
            '.webp': ('image', image_backend),
            '.tiff': ('image', image_backend),
            '.tif':  ('image', image_backend),
            '.heic': ('image', image_backend),
            '.heif': ('image', image_backend),
        }

        self._excel_lock = excel_lock or threading.Lock()
        self._ppt_lock = ppt_lock or threading.Lock()
        self._active_jobs: dict[str, dict[str, Any]] = {}
        self._active_jobs_lock = threading.Lock()

    def _get_backend(self, file_type: str) -> tuple[str, Any]:
        ext = file_type.lower()
        entry = self._backends.get(ext)
        if not entry:
            raise ValueError(f'不支持的文件类型: {ext}')
        return entry

    def print_file(self, filepath: str, file_type: str, job_id: str,
                   word_lock: Optional[threading.Lock],
                   print_params: Optional[dict[str, Any]] = None) -> Any:
        if print_params is None:
            print_params = {}
        backend_name, backend = self._get_backend(file_type)

        lock = word_lock if backend_name == 'office' else None
        params = dict(print_params)

        with self._active_jobs_lock:
            self._active_jobs[job_id] = {'backend_name': backend_name, 'backend': backend}

        try:
            return backend.print_file(filepath, job_id, params, lock=lock)
        finally:
            with self._active_jobs_lock:
                self._active_jobs.pop(job_id, None)

    def cancel_active_job(self, job_id: str) -> bool:
        with self._active_jobs_lock:
            info = self._active_jobs.get(job_id)
            if not info:
                return False
            backend = info['backend']
            backend_info = dict(info)
            del self._active_jobs[job_id]

        return backend.cancel(job_id, backend_info)
