"""打印引擎 — 根据文件类型委托给对应的后端策略"""
import threading
from typing import Any, Optional

from app.printing.backends import OfficeBackend, PdfBackend, ImageBackend
from app.utils import safe_remove

OFFICE_EXTS = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif'}


class PrintEngine:
    """打印调度层，按文件类型分发到不同的 PrinterBackend"""

    def __init__(self, config: Any,
                 excel_lock: threading.Lock,
                 ppt_lock: threading.Lock) -> None:
        self.config = config

        pdf_backend = PdfBackend(config)
        office_backend = OfficeBackend(config, excel_lock, ppt_lock)
        image_backend = ImageBackend(config, pdf_backend)

        self._backends: dict[str, Any] = {}
        for ext in OFFICE_EXTS:
            self._backends[ext] = office_backend
        for ext in IMAGE_EXTS:
            self._backends[ext] = image_backend
        self._backends['.pdf'] = pdf_backend

        self._office_backend = office_backend
        self._pdf_backend = pdf_backend
        self._active_jobs: dict[str, dict[str, Any]] = {}
        self._active_jobs_lock = threading.Lock()

    def _get_backend(self, file_type: str) -> Any:
        ext = file_type.lower()
        backend = self._backends.get(ext)
        if not backend:
            raise ValueError(f'不支持的文件类型: {ext}')
        return backend

    def print_file(self, filepath: str, file_type: str, job_id: str,
                   word_lock: Optional[threading.Lock],
                   print_params: Optional[dict[str, Any]] = None) -> Any:
        if print_params is None:
            print_params = {}
        params = dict(print_params)
        params['_file_type'] = file_type
        ext = file_type.lower()

        if ext in OFFICE_EXTS:
            # Office 文件：先转 PDF，再用 PDF 后端打印
            params['_word_lock'] = word_lock
            pdf_path = self._office_backend.convert_to_pdf(filepath, params)
            try:
                with self._active_jobs_lock:
                    self._active_jobs[job_id] = {'backend': self._pdf_backend}
                return self._pdf_backend.print_file(pdf_path, job_id, params)
            finally:
                with self._active_jobs_lock:
                    self._active_jobs.pop(job_id, None)
                safe_remove(pdf_path)
        else:
            backend = self._get_backend(file_type)
            lock = word_lock if backend is self._office_backend else None
            with self._active_jobs_lock:
                self._active_jobs[job_id] = {'backend': backend}
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
            del self._active_jobs[job_id]

        return backend.cancel(job_id, {})
