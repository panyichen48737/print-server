"""Quick print page: file picker, print options, submit."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from gui.components.drop_zone import DropZoneWidget
from gui.components.stateful_button import StatefulButton
from gui.components.switch_mixin import SWITCH_QSS


class QuickPrintPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("快速打印", styleSheet="font-size: 24px; font-weight: bold;"))

        # Drop zone
        self.drop_zone = DropZoneWidget(self)
        self.drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.drop_zone)

        # Path input + browse
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("文件路径")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_input)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # Print options
        options_row = QHBoxLayout()
        self.printer_combo = QComboBox()
        self.printer_combo.setPlaceholderText("选择打印机")
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)
        self.duplex_cb = QCheckBox("双面")
        self.duplex_cb.setChecked(True)
        self.duplex_cb.setStyleSheet(SWITCH_QSS)
        self.color_cb = QCheckBox("颜色")
        self.color_cb.setChecked(True)
        self.color_cb.setStyleSheet(SWITCH_QSS)
        self.paper_combo = QComboBox()
        self.paper_combo.addItems(["A4", "Letter", "A3"])
        options_row.addWidget(QLabel("打印机:"))
        options_row.addWidget(self.printer_combo)
        options_row.addWidget(QLabel("份数:"))
        options_row.addWidget(self.copies_spin)
        options_row.addWidget(self.duplex_cb)
        options_row.addWidget(self.color_cb)
        options_row.addWidget(QLabel("纸张:"))
        options_row.addWidget(self.paper_combo)
        layout.addLayout(options_row)

        # Progress bar (4 states)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # Submit button
        self.submit_btn = StatefulButton("开始打印")
        self.submit_btn.clicked.connect(self._submit)
        layout.addWidget(self.submit_btn)

        # Tracking label
        self.tracking_label = QLabel("")
        self.tracking_label.setVisible(False)
        layout.addWidget(self.tracking_label)

        layout.addStretch()

        self._file_path: str | None = None
        self._tracking_job_id: int | None = None

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self._on_file_selected(path)

    def _on_file_selected(self, path: str):
        p = Path(path)
        if p.exists():
            self._file_path = str(p)
            self.path_input.setText(str(p))
            self.drop_zone._file_label.setText(f"{p.name} ({p.stat().st_size / 1024:.1f} KB)")

    def _submit(self):
        if not self._file_path:
            return
        self.submit_btn.set_loading()
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate while queuing
        # Upload via backend service (direct call, not HTTP)
        from app.services.upload import save_upload
        file_obj = save_upload(Path(self._file_path))
        if file_obj:
            from app.printing.job_queue import get_queue
            queue = get_queue()
            job = queue.enqueue(
                str(file_obj.path),
                printer=self.printer_combo.currentText(),
                copies=self.copies_spin.value(),
                duplex=self.duplex_cb.isChecked(),
                color=self.color_cb.isChecked(),
                paper_size=self.paper_combo.currentText(),
            )
            self._tracking_job_id = job.id
            self.tracking_label.setText(f"任务 #{job.id} 已提交，等待处理...")
            self.tracking_label.setVisible(True)
            self.progress.setRange(0, 100)
        else:
            self.submit_btn.set_error()
            self.progress.setVisible(False)

    def on_job_status(self, data: dict):
        if data.get("job_id") == self._tracking_job_id:
            status = data.get("status", "")
            if status == "completed":
                self.submit_btn.set_success()
                self.tracking_label.setText(f"任务 #{self._tracking_job_id} 完成")
            elif status == "failed":
                self.submit_btn.set_error()
                self.tracking_label.setText(f"失败: {data.get('error', '')}")
            elif status == "printing":
                self.tracking_label.setText(f"任务 #{self._tracking_job_id} 正在打印...")