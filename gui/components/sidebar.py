"""Sidebar widget: brand, sectioned nav items, status footer."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class SidebarWidget(QFrame):
    """Navigation sidebar with section groups and status footer."""
    currentRowChanged = Signal(int)

    NAV_ITEMS = ["仪表盘", "快速打印", "文档扫描", "任务管理", "实时日志", "设置", "关于"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self.setObjectName("sidebar")
        self._current_row = 0
        self._buttons: list[QPushButton] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Brand header
        brand = QWidget()
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(16, 20, 16, 20)
        bl.setSpacing(0)
        title = QLabel("Print Server")
        title.setObjectName("brandTitle")
        bl.addWidget(title)
        layout.addWidget(brand)

        # Section: 概览
        self._add_section("概览", layout)
        self._add_nav_item("仪表盘", 0, layout)

        # Section: 操作
        self._add_section("操作", layout)
        self._add_nav_item("快速打印", 1, layout)
        self._add_nav_item("文档扫描", 2, layout)
        self._add_nav_item("任务管理", 3, layout)
        self._add_nav_item("实时日志", 4, layout)

        # Section: 管理
        self._add_section("管理", layout)
        self._add_nav_item("设置", 5, layout)
        self._add_nav_item("关于", 6, layout)

        layout.addStretch(1)

        # Footer
        footer = QWidget()
        footer.setObjectName("sidebarFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        fl.setSpacing(8)
        self._footer_dot = QLabel()
        self._footer_dot.setFixedSize(7, 7)
        self._footer_dot.setStyleSheet("background-color: #6B8F6B; border-radius: 3px;")
        self._footer_text = QLabel("运行中\n端口 5000")
        self._footer_text.setObjectName("footerText")
        fl.addWidget(self._footer_dot, alignment=Qt.AlignmentFlag.AlignCenter)
        fl.addWidget(self._footer_text)
        fl.addStretch()
        layout.addWidget(footer)

        self.setCurrentRow(0)

    def set_server_status(self, running: bool, port: int = 5000):
        if running:
            self._footer_dot.setStyleSheet("background-color: #6B8F6B; border-radius: 3px;")
            self._footer_text.setText(f"运行中\n端口 {port}")
        else:
            self._footer_dot.setStyleSheet("background-color: #C53A3A; border-radius: 3px;")
            self._footer_text.setText("已停止")

    def _add_section(self, name: str, layout):
        label = QLabel(name.upper())
        label.setObjectName("sectionLabel")
        layout.addWidget(label)

    def _add_nav_item(self, name: str, index: int, layout):
        btn = QPushButton(name)
        btn.setObjectName("navItem")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda _, i=index: self._on_click(i))
        layout.addWidget(btn)
        self._buttons.append(btn)

    def _on_click(self, index: int):
        self.setCurrentRow(index)

    def setCurrentRow(self, index: int):
        self._current_row = index
        for i, btn in enumerate(self._buttons):
            btn.setProperty("active", i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.currentRowChanged.emit(index)
