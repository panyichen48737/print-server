"""QProgressBar state helpers: indeterminate, success, error."""
from __future__ import annotations

from PySide6.QtWidgets import QProgressBar


class ProgressState:
    """Manages QProgressBar states: indeterminate, success, error, reset."""

    def __init__(self, bar: QProgressBar):
        self._bar = bar

    def set_indeterminate(self, active: bool = True):
        self._bar.setRange(0, 0 if active else 100)
        self._bar.setValue(0)

    def set_success(self):
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.setStyleSheet("""
            QProgressBar { background-color: #E5DDD5; border-radius: 3px; height: 6px; }
            QProgressBar::chunk { background-color: #6B8F6B; border-radius: 3px; }
        """)

    def set_error(self):
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.setStyleSheet("""
            QProgressBar { background-color: #E5DDD5; border-radius: 3px; height: 6px; }
            QProgressBar::chunk { background-color: #C53A3A; border-radius: 3px; }
        """)

    def reset(self):
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setStyleSheet("")
