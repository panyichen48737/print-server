"""QPushButton with loading/success/error states."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QPushButton


class StatefulButton(QPushButton):
    STATES = ("default", "loading", "success", "error", "disabled")

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._original_text = text
        self._state = "default"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reset)

    def set_loading(self):
        self._state = "loading"
        self.setText(f"{self._original_text}...")
        self.setEnabled(False)

    def set_success(self, duration_ms: int = 1500):
        self._state = "success"
        self.setText("✓ " + self._original_text)
        self.setStyleSheet("background-color: #16A34A; color: white;")
        self._timer.start(duration_ms)

    def set_error(self, duration_ms: int = 2000):
        self._state = "error"
        self.setText("✗ 失败")
        self.setStyleSheet("background-color: #DC2626; color: white;")
        self._timer.start(duration_ms)

    def _reset(self):
        self._state = "default"
        self.setText(self._original_text)
        self.setStyleSheet("")
        self.setEnabled(True)