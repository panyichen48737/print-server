"""Real-time log viewer with level filter, source filter, and pause."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.core._paths import log_dir
from gui.components.page_base import PageBase

_LOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(\w+)\]\s+\[([^\]]+)\]\s+(.*)'
)

_SOURCE_COLORS_LIGHT = {
    'Server': QColor('#6B8F6B'),
    'GUI': QColor('#5B7FAF'),
    'Watchdog': QColor('#B8956A'),
    'Update': QColor('#8B7355'),
}
_SOURCE_COLORS_DARK = {
    'Server': QColor('#6B8F6B'),
    'GUI': QColor('#60A5FA'),
    'Watchdog': QColor('#FBBF24'),
    'Update': QColor('#94A3B8'),
}


def _source_color(source: str, dark: bool) -> QColor:
    colors = _SOURCE_COLORS_DARK if dark else _SOURCE_COLORS_LIGHT
    return colors.get(source, QColor('#8A8178'))


class LogsPage(PageBase):
    def __init__(self, main_window, parent=None):
        self._mw = main_window
        self._paused = False
        self._buffer: list[str] = []
        self._max_lines = 1000
        self._dark = False
        super().__init__(parent)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.clear_btn.clicked.connect(self.log_list.clear)
        self.level_filter.currentTextChanged.connect(self._apply_filters)
        self.source_filter.currentTextChanged.connect(self._apply_filters)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._search_timer.start)
        self._load_history()

    def _build_content(self, layout: QVBoxLayout):
        title_lbl = QLabel('实时日志')
        title_lbl.setObjectName('pageTitle')
        layout.addWidget(title_lbl)

        # Controls
        controls = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItems(['全部', '错误', '警告', '信息', '调试'])
        self.source_filter = QComboBox()
        self.source_filter.addItems(['全部来源', 'Server', 'GUI', 'Watchdog', 'Update'])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索...')
        self.pause_btn = QPushButton('暂停')
        self.pause_btn.setObjectName('ghost')
        self.pause_btn.setProperty('compact', True)
        self.clear_btn = QPushButton('清空')
        self.clear_btn.setObjectName('ghostDanger')
        self.clear_btn.setProperty('compact', True)
        self.auto_scroll_cb = QCheckBox('自动滚动')
        self.auto_scroll_cb.setChecked(True)
        controls.addWidget(QLabel('级别:'))
        controls.addWidget(self.level_filter)
        controls.addWidget(QLabel('来源:'))
        controls.addWidget(self.source_filter)
        controls.addWidget(self.search_input)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.clear_btn)
        controls.addWidget(self.auto_scroll_cb)
        self.open_log_btn = QPushButton('📁 打开文件夹')
        self.open_log_btn.setObjectName('ghost')
        self.open_log_btn.setProperty('compact', True)
        self.open_log_btn.clicked.connect(self._open_log_folder)
        controls.addWidget(self.open_log_btn)
        layout.addLayout(controls)

        # Empty state
        self.log_empty_label = QLabel('暂无日志，打印任务时将自动显示')
        self.log_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.log_empty_label.setStyleSheet('color: #8A8178; font-size: 14px; padding: 40px;')
        layout.addWidget(self.log_empty_label)

        # Loading history label
        self.loading_label = QLabel('正在加载历史日志...')
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet('color: #8A8178; font-size: 12px; padding: 12px;')
        self.loading_label.setVisible(False)
        layout.addWidget(self.loading_label)

        # Log list
        self.log_list = QListWidget()
        self.log_list.setVisible(False)
        layout.addWidget(self.log_list)

        # Pause banner
        self.pause_banner = QLabel('')
        self.pause_banner.setVisible(False)
        self.pause_banner.setStyleSheet(
            'background-color: #E8DFD4; color: #8B7355; padding: 4px 12px; border-radius: 6px;'
        )
        layout.addWidget(self.pause_banner)

    def _log_files(self) -> list[tuple[Path, str]]:
        ld = log_dir()
        return [
            (ld / 'app.log', 'Server'),
            (ld / 'update_service.log', 'Update'),
            (ld / 'watchdog.log', 'Watchdog'),
        ]

    def _parse_line(self, line: str, default_source: str) -> dict | None:
        m = _LOG_PATTERN.match(line)
        if m:
            ts, level, source, msg = m.groups()
            return {'timestamp': ts, 'level': level.upper(), 'source': source, 'message': msg}
        m2 = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(\w+)\]\s+(.*)', line)
        if m2:
            return {
                'timestamp': m2.group(1),
                'level': m2.group(2).upper(),
                'source': default_source,
                'message': m2.group(3),
            }
        m3 = re.match(r'^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})\s+(.*)', line)
        if m3:
            return {
                'timestamp': m3.group(1).replace('/', '-'),
                'level': 'INFO',
                'source': default_source,
                'message': m3.group(2),
            }
        return {'timestamp': '', 'level': 'INFO', 'source': default_source, 'message': line}

    def _load_history(self):
        self.loading_label.setVisible(True)
        entries: list[dict] = []

        for file_path, src in self._log_files():
            if not file_path.exists():
                continue
            try:
                with file_path.open('r', encoding='utf-8', errors='replace') as f:
                    for raw in f.readlines()[-200:]:
                        raw = raw.rstrip('\n')
                        if not raw:
                            continue
                        parsed = self._parse_line(raw, src)
                        if parsed:
                            entries.append(parsed)
            except OSError:
                continue

        entries.sort(key=lambda e: (e['timestamp'] or '', e['message'] or ''))
        self.loading_label.setVisible(False)
        for entry in entries:
            self.on_log(entry)

    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_btn.setText('继续' if self._paused else '暂停')
        if not self._paused:
            for line in self._buffer:
                self._append_line(line)
            self._buffer.clear()
            self.pause_banner.setVisible(False)

    def _format_item(self, data: dict) -> str:
        ts = data.get('timestamp', '')
        level = data.get('level', 'INFO')
        source = data.get('source', '')
        msg = data.get('message', '')
        return f'{ts}  [{level}]  [{source}]  {msg}'

    def _append_line(self, text: str):
        item = QListWidgetItem(text)
        from gui.theme import ThemeEngine

        theme = ThemeEngine.instance()
        dark = theme.mode == 'dark'
        source = ''
        m = re.search(r'\[([^\]]+)\]  \[([^\]]+)\]', text)
        if m:
            source = m.group(2)
        item.setForeground(_source_color(source, dark))
        if '[ERROR]' in text or '[WARNING]' in text:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        self.log_list.addItem(item)
        if self.log_list.count() > self._max_lines:
            self.log_list.takeItem(0)
        if self.auto_scroll_cb.isChecked():
            self.log_list.scrollToBottom()

    def on_log(self, data: dict):
        self.log_empty_label.setVisible(False)
        self.log_list.setVisible(True)
        msg = self._format_item(data)
        if self._paused:
            self._buffer.append(msg)
            self.pause_banner.setText(f'⏸ 已暂停 (+{len(self._buffer)} 条)')
            self.pause_banner.setVisible(True)
        else:
            self._append_line(msg)

    def _apply_filters(self):
        level = self.level_filter.currentText()
        source = self.source_filter.currentText()
        search = self.search_input.text().lower()
        for i in range(self.log_list.count()):
            item = self.log_list.item(i)
            if not item:
                continue
            text = item.text()
            visible = True
            if level != '全部':
                level_map = {'错误': 'ERROR', '警告': 'WARNING', '信息': 'INFO', '调试': 'DEBUG'}
                if level_map.get(level, '') not in text:
                    visible = False
            if source != '全部来源':
                src_tag = f'[{source}]'
                if src_tag not in text:
                    visible = False
            if search and search not in text.lower():
                visible = False
            item.setHidden(not visible)

    def _open_log_folder(self):
        import subprocess

        ld = log_dir()
        if ld.exists():
            subprocess.Popen(['explorer', str(ld)], shell=True)
