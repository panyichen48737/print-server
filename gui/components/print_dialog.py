"""Modal print settings dialog, shares PrinterCapabilities with inline panel."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from gui.components.printer_capabilities import (
    PrinterCapabilities, query_capabilities,
)
from gui.components.toggle_switch import LabeledToggle


class PrintDialog(QDialog):
    def __init__(self, printers: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("打印设置")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._caps: PrinterCapabilities = PrinterCapabilities()
        self._result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Printer
        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("打印机:"))
        self.printer_combo = QComboBox()
        self.printer_combo.addItems(printers)
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)
        printer_row.addWidget(self.printer_combo, 1)
        layout.addLayout(printer_row)

        # Copies
        copies_row = QHBoxLayout()
        copies_row.addWidget(QLabel("份数:"))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)
        copies_row.addWidget(self.copies_spin)
        copies_row.addStretch()
        layout.addLayout(copies_row)

        # Color
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("颜色:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["彩色", "黑白"])
        color_row.addWidget(self.color_combo)
        color_row.addStretch()
        layout.addLayout(color_row)

        # Duplex
        self.duplex_cb = LabeledToggle("双面", checked=True)
        layout.addWidget(self.duplex_cb)

        # Paper
        paper_row = QHBoxLayout()
        paper_row.addWidget(QLabel("纸张:"))
        self.paper_combo = QComboBox()
        paper_row.addWidget(self.paper_combo)
        paper_row.addStretch()
        layout.addLayout(paper_row)

        # Buttons
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        self.confirm_btn = QPushButton("确认打印")
        self.confirm_btn.setObjectName("primary")
        self.confirm_btn.clicked.connect(self._confirm)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.confirm_btn)
        layout.addLayout(btn_row)

        if printers:
            self.printer_combo.setCurrentIndex(0)

    def _on_printer_changed(self, name: str):
        if not name:
            return
        self._caps = query_capabilities(name)
        self.copies_spin.setRange(1, self._caps.copies_max)

        # Color
        self.color_combo.clear()
        if self._caps.supports_color:
            self.color_combo.addItems(["彩色", "黑白"])
        else:
            self.color_combo.addItems(["黑白"])

        # Duplex
        self.duplex_cb.setVisible(self._caps.supports_duplex)
        self.duplex_cb.setChecked(self._caps.supports_duplex)

        # Paper
        self.paper_combo.clear()
        self.paper_combo.addItems(self._caps.paper_names)
        if "A4" in self._caps.paper_names:
            self.paper_combo.setCurrentText("A4")

    def _confirm(self):
        self._result = {
            "printer": self.printer_combo.currentText(),
            "copies": self.copies_spin.value(),
            "color": self.color_combo.currentText() == "彩色",
            "duplex": self.duplex_cb.isChecked() if self.duplex_cb.isVisible() else False,
            "paper_size": self.paper_combo.currentText(),
        }
        self.accept()

    def get_result(self) -> dict | None:
        return self._result
