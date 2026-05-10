"""打印引擎 — 根据文件类型委托给对应的后端策略"""

from __future__ import annotations

import sys
import threading
from typing import Any

from app.core.exceptions import FileTypeError
from app.core.utils import safe_remove
from app.printing.backends import (  # noqa: F401 保留命名空间供测试 mock
    ImageBackend,
    OfficeBackend,
    PdfBackend,
    PrinterBackend,
    discover_backends,
)

# 以便测试用 @patch('app.printing.engine.OfficeBackend') 替换


class PrintEngine:
    """打印调度层，按文件类型分发到不同的 PrinterBackend"""

    def __init__(self, config: Any, excel_lock: threading.Lock, ppt_lock: threading.Lock) -> None:
        self.config = config
        self._excel_lock = excel_lock
        self._ppt_lock = ppt_lock

        self._backends: dict[str, PrinterBackend] = {}
        self._instances: dict[type, PrinterBackend] = {}
        office_instance = None
        pdf_instance = None
        for ext, cls in discover_backends().items():
            if cls not in self._instances:
                self._instances[cls] = self._build_instance(cls)
            self._backends[ext] = self._instances[cls]
            if cls.__name__ == 'OfficeBackend':
                office_instance = self._instances[cls]
            elif cls.__name__ == 'PdfBackend':
                pdf_instance = self._instances[cls]

        self._office_backend = office_instance
        self._pdf_backend = pdf_instance
        self._active_jobs: dict[str, dict[str, Any]] = {}
        self._active_jobs_lock = threading.Lock()

    def _build_instance(self, cls: type[PrinterBackend]) -> PrinterBackend:
        mod = sys.modules[__name__]
        target = getattr(mod, cls.__name__, cls)
        name = cls.__name__
        if name == 'PdfBackend':
            return target(self.config)
        if name == 'OfficeBackend':
            return target(self.config, self._excel_lock, self._ppt_lock)
        if name == 'ImageBackend':
            pdf_inst = None
            for existing_cls, inst in self._instances.items():
                if existing_cls.__name__ == 'PdfBackend':
                    pdf_inst = inst
                    break
            if pdf_inst is None:
                # 查找真实 PdfBackend 类
                for reg_cls in discover_backends().values():
                    if reg_cls.__name__ == 'PdfBackend':
                        pdf_inst = self._build_instance(reg_cls)
                        self._instances[reg_cls] = pdf_inst
                        break
            return target(self.config, pdf_inst)
        return target(self.config)

    def _get_backend(self, file_type: str) -> Any:
        ext = file_type.lower()
        backend = self._backends.get(ext)
        if not backend:
            raise FileTypeError(f'不支持的文件类型: {ext}')
        return backend

    def print_file(
        self,
        filepath: str,
        file_type: str,
        job_id: str,
        word_lock: threading.Lock | None,
        print_params: dict[str, Any] | None = None,
    ) -> Any:
        if print_params is None:
            print_params = {}
        params = dict(print_params)
        params['_file_type'] = file_type
        ext = file_type.lower()

        target_backend = self._backends.get(ext)
        if target_backend is self._office_backend and self._office_backend is not None:
            # Office 文件：先转 PDF，再用 PDF 后端打印
            params['_word_lock'] = word_lock
            pdf_path = self._office_backend.convert_to_pdf(filepath, params)  # type: ignore
            try:
                with self._active_jobs_lock:
                    self._active_jobs[job_id] = {'backend': self._pdf_backend}
                return self._pdf_backend.print_file(pdf_path, job_id, params)  # type: ignore
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
