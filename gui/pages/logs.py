"""Real-time log viewer with level filter and pause."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)


LOG_COLORS = {
    "ERROR": QColor("#DC2626"),
    "WARNING": QColor("#F59E0B"),
    "INFO": QColor("#2563EB"),
    "DEBUG": QColor("#6B7280"),
}


class LogsPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("实时日志", styleSheet="font-size: 24px; font-weight: bold;"))

        # Controls
        controls = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "错误", "警告", "信息", "调试"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.pause_btn = QPushButton("暂停")
        self.clear_btn = QPushButton("清空")
        self.auto_scroll_cb = QCheckBox("自动滚动")
        self.auto_scroll_cb.setChecked(True)
        controls.addWidget(QLabel("级别:"))
        controls.addWidget(self.level_filter)
        controls.addWidget(self.search_input)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.clear_btn)
        controls.addWidget(self.auto_scroll_cb)
        layout.addLayout(controls)

        # Empty state
        self.log_empty_label = QLabel("暂无日志，打印任务时将自动显示")
        self.log_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.log_empty_label.setStyleSheet("color: #9CA3AF; font-size: 14px; padding: 40px;")
        layout.addWidget(self.log_empty_label)

        # Log list
        self.log_list = QListWidget()
        self.log_list.setVisible(False)
        layout.addWidget(self.log_list)

        # Pause banner
        self.pause_banner = QLabel("")
        self.pause_banner.setVisible(False)
        self.pause_banner.setStyleSheet(
            "background-color: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 4px;"
        )
        layout.addWidget(self.pause_banner)

        self._paused = False
        self._buffer: list[str] = []
        self._max_lines = 1000

        self.pause_btn.clicked.connect(self._toggle_pause)
        self.clear_btn.clicked.connect(self.log_list.clear)
        self.level_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)

    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_btn.setText("继续" if self._paused else "暂停")
        if not self._paused:
            for line in self._buffer:
                self._append_line(line)
            self._buffer.clear()
            self.pause_banner.setVisible(False)

    def _append_line(self, text: str):
        item = QListWidgetItem(text)
        for level, color in LOG_COLORS.items():
            if level in text:
                item.setForeground(color)
                break
        self.log_list.addItem(item)
        if self.log_list.count() > self._max_lines:
            self.log_list.takeItem(0)
        if self.auto_scroll_cb.isChecked():
            self.log_list.scrollToBottom()

    def on_log(self, data: dict):
        self.log_empty_label.setVisible(False)
        self.log_list.setVisible(True)
        msg = f'{data.get("timestamp", "")}  {data.get("level", "INFO")}  {data.get("message", "")}'
        if self._paused:
            self._buffer.append(msg)
            self.pause_banner.setText(f"⏸ 已暂停 (+{len(self._buffer)} 条)")
            self.pause_banner.setVisible(True)
        else:
            self._append_line(msg)

    def _apply_filters(self):
        level = self.level_filter.currentText()
        search = self.search_input.text().lower()
        for i in range(self.log_list.count()):
            item = self.log_list.item(i)
            if not item:
                continue
            text = item.text()
            visible = True
            if level != "全部":
                level_map = {"错误": "ERROR", "警告": "WARNING", "信息": "INFO", "调试": "DEBUG"}
                if level_map.get(level, "") not in text:
                    visible = False
            if search and search not in text.lower():
                visible = False
            item.setHidden(not visible)