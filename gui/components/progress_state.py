"""QProgressBar state helpers: indeterminate, success, error."""
from __future__ import annotations

from PySide6.QtWidgets import QProgressBar


def set_indeterminate(bar: QProgressBar, active: bool = True):
    bar.setRange(0, 0 if active else 100)
    bar.setValue(0)


def set_success(bar: QProgressBar):
    bar.setRange(0, 100)
    bar.setValue(100)
    bar.setStyleSheet("""
        QProgressBar { background-color: #E5DDD5; border-radius: 3px; height: 6px; }
        QProgressBar::chunk { background-color: #6B8F6B; border-radius: 3px; }
    """)


def set_error(bar: QProgressBar):
    bar.setRange(0, 100)
    bar.setValue(100)
    bar.setStyleSheet("""
        QProgressBar { background-color: #E5DDD5; border-radius: 3px; height: 6px; }
        QProgressBar::chunk { background-color: #C53A3A; border-radius: 3px; }
    """)


def reset(bar: QProgressBar):
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setStyleSheet("")