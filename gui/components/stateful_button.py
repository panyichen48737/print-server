"""QPushButton with loading/success/error states."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QPushButton


class StatefulButton(QPushButton):
    STATES = ("default", "loading", "success", "error", "disabled")

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("primary")
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
        self.setStyleSheet("background-color: #6B8F6B; color: white; border: none;")
        self._timer.start(duration_ms)

    def set_error(self, error_msg: str = "", duration_ms: int = 2000):
        self._state = "error"
        self.setText("✗ 失败")
        self.setStyleSheet("background-color: #C53A3A; color: white; border: none;")
        if error_msg:
            self.setToolTip(error_msg)
        self._timer.start(duration_ms)

    def reset(self):
        """Public reset — return to default state."""
        self._reset()

    def _reset(self):
        self._state = "default"
        self.setText(self._original_text)
        self.setStyleSheet("")
        self.setToolTip("")
        self.setEnabled(True)
        # 恢复 QSS 主题样式
        style = self.style()
        if style:
            style.unpolish(self)
            style.polish(self)