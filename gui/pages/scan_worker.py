"""Scan worker: background Quark API enhancement thread."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class ScanWorker(QThread):
    """Background worker for Quark API enhancement."""
    progress = Signal(int, int)
    finished = Signal(int, list)
    error = Signal(str)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.paths = paths
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from app.core.config import Config
        from app.services.image_processing import QuarkEnhancer

        config = Config()
        enhancer = QuarkEnhancer(config)
        results: list[tuple[str, bytes | None]] = []

        for i, path in enumerate(self.paths):
            if self._cancelled:
                break
            self.progress.emit(i + 1, len(self.paths))
            try:
                enhanced = enhancer.enhance(path)
                results.append((path, enhanced))
            except Exception:
                results.append((path, None))

        self.finished.emit(len(self.paths), results)
