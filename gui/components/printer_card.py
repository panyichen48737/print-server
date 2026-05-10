"""Printer card widget — compact (dashboard) and full (manager) modes."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class PrinterCardWidget(QFrame):
    set_default_clicked = Signal(str)

    STATUS_COLORS = {
        'ready': '#6B8F6B',
        'busy': '#D4A84B',
        'error': '#C53A3A',
    }
    STATUS_TEXTS = {
        'ready': '就绪',
        'busy': '忙碌',
        'error': '错误',
    }

    def __init__(
        self,
        name: str,
        status: str,
        port: str = '',
        is_default: bool = False,
        compact: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._name = name
        self.setObjectName('printerCard')
        self.setProperty('compact', compact)

        color = self.STATUS_COLORS.get(status, '#999999')
        status_text = self.STATUS_TEXTS.get(status, status)

        if compact:
            self._build_compact(name, port, color, status_text)
        else:
            self._build_full(name, port, color, status_text, is_default)

    def _build_compact(self, name: str, port: str, color: str, status_text: str):
        lo = QHBoxLayout(self)
        lo.setContentsMargins(18, 14, 18, 14)
        lo.setSpacing(10)

        # Icon
        icon = QLabel('🖨')
        icon.setStyleSheet('font-size: 16px;')

        # Name + port
        info = QWidget()
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(1)
        nl = QLabel(name)
        nl.setObjectName('printName')
        il.addWidget(nl)
        if port:
            pl = QLabel(port)
            pl.setObjectName('printPort')
            il.addWidget(pl)

        lo.addWidget(icon)
        lo.addWidget(info)
        lo.addStretch()

        # Status dot + text
        sw = QWidget()
        sl = QHBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(5)
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f'background-color: {color}; border-radius: 3px;')
        st = QLabel(status_text)
        st.setStyleSheet(f'font-size: 11px; font-weight: 600; color: {color};')
        sl.addWidget(dot)
        sl.addWidget(st)
        lo.addWidget(sw)

    def _build_full(self, name: str, port: str, color: str, status_text: str, is_default: bool):
        lo = QVBoxLayout(self)
        lo.setContentsMargins(18, 18, 18, 18)
        lo.setSpacing(10)

        # Icon + name row
        top = QHBoxLayout()
        icon = QLabel('🖨')
        icon.setStyleSheet('font-size: 20px;')
        nl = QLabel(name)
        nl.setObjectName('printName')
        top.addWidget(icon)
        top.addWidget(nl)
        top.addStretch()
        lo.addLayout(top)

        if port:
            pl = QLabel(port)
            pl.setObjectName('printPort')
            lo.addWidget(pl)

        # Status
        sw = QWidget()
        sl = QHBoxLayout(sw)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(5)
        dot = QLabel()
        dot.setFixedSize(7, 7)
        dot.setStyleSheet(f'background-color: {color}; border-radius: 3px;')
        st = QLabel(status_text)
        st.setStyleSheet(f'font-size: 12px; font-weight: 600; color: {color};')
        sl.addWidget(dot)
        sl.addWidget(st)

        if is_default:
            sl.addStretch()
            dl = QLabel('★ 默认')
            dl.setObjectName('printDefaultBadge')
            sl.addWidget(dl)

        lo.addWidget(sw)
        lo.addStretch()

        # Button
        if is_default:
            btn = QPushButton('已设为默认')
            btn.setObjectName('ghost')
            btn.setEnabled(False)
        else:
            btn = QPushButton('设为默认')
            btn.setObjectName('primary')
            btn.clicked.connect(lambda: self.set_default_clicked.emit(self._name))
        lo.addWidget(btn)
