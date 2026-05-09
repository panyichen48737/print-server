"""Drag-and-drop zone for file selection."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DropZoneWidget(QWidget):
    file_dropped = Signal(str)

    def _update_style(self):
        from gui.theme import ThemeEngine
        t = ThemeEngine.instance().tokens
        self.setStyleSheet(f"""
            DropZoneWidget {{
                border: 2px dashed {t['outline']};
                border-radius: 12px;
                background-color: transparent;
            }}
            DropZoneWidget[drag_over="true"] {{
                border-color: {t['primary']};
            }}
        """)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(200)
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label = QLabel("☁")
        self._file_label = QLabel("")
        self._text_label = QLabel("拖拽文件到此处")
        for lb in (self._icon_label, self._text_label, self._file_label):
            lb.setStyleSheet("background: transparent;")
        layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._text_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._file_label, alignment=Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_over", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
            if path:
                self._set_file(path)
                self.file_dropped.emit(path)

    def _set_file(self, path: str):
        p = Path(path)
        if p.exists():
            self._file_label.setText(f"{p.name} ({p.stat().st_size / 1024:.1f} KB)")