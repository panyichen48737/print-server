"""Printer card widget showing name, status, and controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class PrinterCardWidget(QFrame):
    set_default_clicked = Signal(str)

    def __init__(self, name: str, status: str, is_default: bool = False, parent=None):
        super().__init__(parent)
        self._name = name
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(260, 120)

        layout = QVBoxLayout(self)
        # Name + status dot
        header = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {'green' if status == 'ready' else 'orange'}; font-size: 18px;")
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(dot)
        header.addWidget(name_label)
        header.addStretch()
        layout.addLayout(header)

        status_label = QLabel(f"状态: {status}")
        status_label.setStyleSheet("color: gray;")
        layout.addWidget(status_label)

        if is_default:
            default_label = QLabel("★ 默认打印机")
            default_label.setStyleSheet("color: #16A34A; font-weight: bold;")
            layout.addWidget(default_label)
        else:
            btn = QPushButton("设为默认")
            btn.clicked.connect(lambda: self.set_default_clicked.emit(self._name))
            layout.addWidget(btn)

        layout.addStretch()