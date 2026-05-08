"""Skeleton loading placeholder widget."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class SkeletonWidget(QWidget):
    def __init__(self, width: int = 100, height: int = 20, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._opacity = 0.3
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(800)
        self._direction = 1

    def _pulse(self):
        self._opacity += 0.05 * self._direction
        if self._opacity >= 0.5:
            self._direction = -1
        elif self._opacity <= 0.15:
            self._direction = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(200, 200, 200, int(255 * self._opacity)))
        painter.end()