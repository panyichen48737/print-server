"""Real-time log viewer with level filter and pause."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app._paths import persistent_dir


LOG_COLORS = {
    "ERROR": QColor("#C53A3A"),
    "WARNING": QColor("#B8956A"),
    "INFO": QColor("#8B7355"),
    "DEBUG": QColor("#8A8178"),
}


class LogsPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("dashboardScroll")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 28, 32, 28)

        title_lbl = QLabel("实时日志")
        title_lbl.setObjectName("pageTitle")
        layout.addWidget(title_lbl)

        # Controls
        controls = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "错误", "警告", "信息", "调试"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setObjectName("ghost")
        self.pause_btn.setProperty("compact", True)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("ghostDanger")
        self.clear_btn.setProperty("compact", True)
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
        self.log_empty_label.setStyleSheet("color: #8A8178; font-size: 14px; padding: 40px;")
        layout.addWidget(self.log_empty_label)

        # Loading history label
        self.loading_label = QLabel("正在加载历史日志...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #8A8178; font-size: 12px; padding: 12px;")
        self.loading_label.setVisible(False)
        layout.addWidget(self.loading_label)

        # Log list
        self.log_list = QListWidget()
        self.log_list.setVisible(False)
        layout.addWidget(self.log_list)

        # Pause banner
        self.pause_banner = QLabel("")
        self.pause_banner.setVisible(False)
        self.pause_banner.setStyleSheet(
            "background-color: #E8DFD4; color: #8B7355; padding: 4px 12px; border-radius: 6px;"
        )
        layout.addWidget(self.pause_banner)

        self._paused = False
        self._buffer: list[str] = []
        self._max_lines = 1000

        self.pause_btn.clicked.connect(self._toggle_pause)
        self.clear_btn.clicked.connect(self.log_list.clear)
        self.level_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        self._load_history()

    def _load_history(self):
        self.loading_label.setVisible(True)
        log_path = Path(persistent_dir()) / "logs" / "print_server.log"
        if not log_path.exists():
            self.loading_label.setVisible(False)
            return
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-200:]
        except OSError:
            self.loading_label.setVisible(False)
            return
        self.loading_label.setVisible(False)
        for line in lines:
            line = line.rstrip("\n")
            if not line:
                continue
            level = "INFO"
            for lv in ("ERROR", "WARNING", "INFO", "DEBUG"):
                if lv in line:
                    level = lv
                    break
            self.on_log({"timestamp": "", "level": level, "message": line})

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