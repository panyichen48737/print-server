"""Printer management page: card grid with status, refresh, set default."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from gui.components.printer_card import PrinterCardWidget


class PrinterManagerPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._event_bus = getattr(main_window, "_event_bus", None)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("dashboardScroll")

        container = QWidget()
        lo = QVBoxLayout(container)
        lo.setContentsMargins(28, 28, 32, 28)
        lo.setSpacing(0)

        # Title toolbar
        toolbar = QHBoxLayout()
        title_lbl = QLabel("打印机管理")
        title_lbl.setObjectName("pageTitle")
        toolbar.addWidget(title_lbl)
        toolbar.addStretch()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("ghost")
        self.refresh_btn.clicked.connect(self._refresh_printers)
        toolbar.addWidget(self.refresh_btn)
        lo.addLayout(toolbar)
        lo.addSpacing(28)

        # Printer card grid
        self.card_grid = QGridLayout()
        self.card_grid.setSpacing(16)
        lo.addLayout(self.card_grid)

        # Empty state
        self.empty_label = QLabel("未检测到打印机")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #8A8178; font-size: 14px; padding: 40px;")
        lo.addWidget(self.empty_label)

        # Loading state
        self.loading_label = QLabel("正在检测打印机...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #8A8178; font-size: 14px; padding: 20px;")
        self.loading_label.setVisible(False)
        lo.addWidget(self.loading_label)

        # Error state
        self.error_label = QLabel("")
        self.error_label.setVisible(False)
        lo.addWidget(self.error_label)

        lo.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        QTimer.singleShot(500, self._refresh_printers)

    def _refresh_printers(self):
        self.loading_label.setVisible(True)
        self.error_label.setVisible(False)
        self.empty_label.setVisible(False)
        self.refresh_btn.setEnabled(False)
        try:
            for i in reversed(range(self.card_grid.count())):
                item = self.card_grid.itemAt(i)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
                self.card_grid.removeItem(item)

            monitor = getattr(self._mw._app.state, "printer_monitor", None)
            if monitor is None:
                self.error_label.setText("打印机监控未初始化")
                self.error_label.setVisible(True)
                return
            raw = monitor.get_all_statuses()
            if not raw:
                self.empty_label.setVisible(True)
            else:
                cols = 2
                config = getattr(self._mw, "_config", None)
                default_printer = config.get("default_printer", "") if config else ""
                for idx, (name, info) in enumerate(raw.items()):
                    overall = info.get("overall", "ready")
                    port = info.get("port", "")
                    card = PrinterCardWidget(name, overall, port=port,
                                             is_default=(name == default_printer), compact=False)
                    card.set_default_clicked.connect(self._set_default_printer)
                    self.card_grid.addWidget(card, idx // cols, idx % cols)
        except Exception as e:
            self.error_label.setText(f"刷新打印机失败: {e}")
            self.error_label.setVisible(True)
        finally:
            self.loading_label.setVisible(False)
            self.refresh_btn.setEnabled(True)

    def _set_default_printer(self, name: str):
        config = getattr(self._mw, "_config", None)
        if config is None:
            return
        config.set("default_printer", name)
        config.save()
        self._refresh_printers()

    def on_printer_status(self, data: dict):
        pass
