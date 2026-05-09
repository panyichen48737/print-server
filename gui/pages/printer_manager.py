"""Printer management page: card grid with status, refresh, set default."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from gui.components.printer_card import PrinterCardWidget


class PrinterManagerPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._event_bus = getattr(main_window, "_event_bus", None)
        layout = QVBoxLayout(self)

        # Title toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("打印机管理", styleSheet="font-size: 24px; font-weight: bold;"))
        toolbar.addStretch()
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self._refresh_printers)
        toolbar.addWidget(self.refresh_btn)
        layout.addLayout(toolbar)

        # Printer card grid
        self.card_grid = QGridLayout()
        self.card_grid.setSpacing(12)
        layout.addLayout(self.card_grid)

        # Empty state
        self.empty_label = QLabel("未检测到打印机")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #9CA3AF; font-size: 14px; padding: 40px;")
        layout.addWidget(self.empty_label)

        # Loading state
        self.loading_label = QLabel("正在检测打印机...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #6B7280; font-size: 14px; padding: 20px;")
        self.loading_label.setVisible(False)
        layout.addWidget(self.loading_label)

        # Error state
        self.error_label = QLabel("")
        self.error_label.setVisible(False)
        self.error_label.setStyleSheet(
            "background-color: #FEE2E2; color: #DC2626; padding: 8px 16px; border-radius: 4px;"
        )
        layout.addWidget(self.error_label)

        layout.addStretch()

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

            printers = self._mw._app.state.printer_monitor.get_printers()

            if not printers:
                self.empty_label.setVisible(True)
            else:
                cols = 2
                for idx, info in enumerate(printers):
                    card = PrinterCardWidget(info)
                    self.card_grid.addWidget(card, idx // cols, idx % cols)
        except Exception as e:
            self.error_label.setText(f"刷新打印机失败: {e}")
            self.error_label.setVisible(True)
        finally:
            self.loading_label.setVisible(False)
            self.refresh_btn.setEnabled(True)

    def on_printer_status(self, data: dict):
        # Stub — will update card grid when connected
        pass