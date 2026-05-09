"""Quick print page: file picker (drag/drop + click), multi-file, batch submit."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from gui.components.drop_zone import DropZoneWidget
from gui.components.stateful_button import StatefulButton
from gui.components.toggle_switch import LabeledToggle
from gui.components.printer_capabilities import query_capabilities


IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".heic", ".heif"]


class _FileItemWidget(QWidget):
    """Custom widget for a file list item with thumbnail, path, open and delete buttons."""

    def __init__(self, file_path: str, list_widget: QListWidget, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._list_widget = list_widget
        self.setMinimumHeight(48)
        p = Path(file_path)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 4, 8, 4)
        lo.setSpacing(10)

        from PySide6.QtGui import QPixmap
        from PySide6.QtCore import Qt

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if p.suffix.lower() in IMAGE_EXTS:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("\U0001f5bc")
        else:
            thumb.setText("\U0001f4c4")
        lo.addWidget(thumb)

        # File name + truncated path
        parent_dir = p.parent.name if p.parent.name else p.parent.drive
        display_path = f"{parent_dir}\\{p.name}"
        if len(display_path) > 55:
            display_path = f"{parent_dir[0]}...\\{p.name}"
        info = QLabel(p.name)
        info.setToolTip(str(p))
        info.setStyleSheet("font-size: 12px; color: #8A8178;")

        path_lbl = QLabel(display_path)
        path_lbl.setToolTip(str(p))
        path_lbl.setStyleSheet("font-size: 11px; color: #6B7280;")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(info)
        text_col.addWidget(path_lbl)
        lo.addLayout(text_col, 1)

        open_btn = QPushButton("打开")
        open_btn.setFixedWidth(50)
        open_btn.setObjectName("ghost")
        open_btn.setProperty("compact", True)
        open_btn.clicked.connect(self._open_file)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setObjectName("ghostDanger")
        del_btn.setProperty("compact", True)
        del_btn.clicked.connect(self._delete_self)
        lo.addWidget(open_btn)
        lo.addWidget(del_btn)

    def _open_file(self):
        import subprocess
        subprocess.Popen(["explorer", self.file_path], shell=True)

    def _delete_self(self):
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            w = self._list_widget.itemWidget(item)
            if w is self:
                self._list_widget.takeItem(i)
                break


class QuickPrintPage(QWidget):
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
        layout.setSpacing(12)

        title_lbl = QLabel("快速打印")
        title_lbl.setObjectName("pageTitle")

        title_row = QHBoxLayout()
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        self.clear_btn = QPushButton("✕ 清除")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.setToolTip("清除所有已选文件和结果，重新开始")
        self.clear_btn.clicked.connect(self._confirm_clear)
        title_row.addWidget(self.clear_btn)
        layout.addLayout(title_row)

        # Drop zone — click to browse or drag & drop (multi-file, filtered)
        self.drop_zone = DropZoneWidget(self)
        self.drop_zone.files_selected.connect(self._on_files_selected)
        layout.addWidget(self.drop_zone)

        # File list
        self.file_list = QListWidget()
        self.file_list.setVisible(False)
        self.file_list.setMinimumHeight(80)
        self.file_list.setMaximumHeight(250)
        layout.addWidget(self.file_list)

        # Print options
        options_row = QHBoxLayout()
        self.printer_combo = QComboBox()
        self.printer_combo.setPlaceholderText("选择打印机")
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)
        self.duplex_cb = LabeledToggle("双面", checked=True)
        self.color_combo = QComboBox()
        self.color_combo.addItems(["彩色", "黑白"])
        self.paper_combo = QComboBox()
        self.paper_combo.addItems(["A4", "Letter", "A3"])
        options_row.addWidget(QLabel("打印机:"))
        options_row.addWidget(self.printer_combo)
        options_row.addWidget(QLabel("份数:"))
        options_row.addWidget(self.copies_spin)
        options_row.addWidget(self.duplex_cb)
        options_row.addWidget(self.color_combo)
        options_row.addWidget(QLabel("纸张:"))
        options_row.addWidget(self.paper_combo)
        layout.addLayout(options_row)

        self.drop_zone.setToolTip("支持 PDF、Office 文档、图片文件，可拖拽或多选")
        self.copies_spin.setToolTip("设置打印份数，最大不超过打印机支持上限")
        self.duplex_cb.setToolTip("开启后打印机将双面打印（需打印机支持）")

        # Progress bar
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
        self.tracking_label.setWordWrap(True)
        layout.addWidget(self.tracking_label)

        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        self._file_paths: list[str] = []
        self._tracking_job_ids: list[int] = []

        # Refresh printers on init
        QTimer.singleShot(300, self._refresh_printers)
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)

    def _refresh_printers(self):
        monitor = getattr(self._mw._app.state, "printer_monitor", None)
        if monitor is None:
            return
        self.printer_combo.clear()
        raw = monitor.get_all_statuses()
        for name in raw:
            self.printer_combo.addItem(name)

        # Auto-select default
        try:
            import win32print
            default = win32print.GetDefaultPrinter()
            idx = self.printer_combo.findText(default)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _on_printer_changed(self, name: str):
        if not name:
            return
        caps = query_capabilities(name)
        self.copies_spin.setRange(1, caps.copies_max)
        self.copies_spin.setToolTip(f"最大复印数: {caps.copies_max}")

        self.color_combo.clear()
        if caps.supports_color:
            self.color_combo.addItems(["彩色", "黑白"])
            self.color_combo.setCurrentText("彩色")
        else:
            self.color_combo.addItems(["黑白"])

        self.duplex_cb.setVisible(caps.supports_duplex)
        if not caps.supports_duplex:
            self.duplex_cb.setChecked(False)

        self.paper_combo.clear()
        self.paper_combo.addItems(caps.paper_names)
        if "A4" in caps.paper_names:
            self.paper_combo.setCurrentText("A4")

    def _confirm_clear(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认清除", "确定要清除所有已选文件吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_all()

    def _clear_all(self):
        self._file_paths.clear()
        self._tracking_job_ids.clear()
        self.file_list.clear()
        self.file_list.setVisible(False)
        self.progress.setVisible(False)
        self.tracking_label.setVisible(False)
        self.tracking_label.setText("")
        self.submit_btn.reset()

    def _has_unsaved_content(self) -> bool:
        return self.file_list.count() > 0

    def _on_files_selected(self, paths: list[str]):
        self._file_paths = paths
        self.file_list.clear()
        for p in paths:
            item = QListWidgetItem()
            w = _FileItemWidget(p, self.file_list)
            item.setSizeHint(w.sizeHint())
            self.file_list.addItem(item)
            self.file_list.setItemWidget(item, w)
        self.file_list.setVisible(len(paths) > 0)

    def _get_current_paths(self) -> list[str]:
        paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            w = self.file_list.itemWidget(item)
            if w and hasattr(w, "file_path"):
                paths.append(w.file_path)
        return paths

    def _submit(self):
        paths = self._get_current_paths()
        if not paths:
            return
        self.submit_btn.set_loading()
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._tracking_job_ids.clear()

        from app.services.upload import save_upload
        from app.printing.job_queue import get_queue

        queue = get_queue()
        total = len(paths)
        submitted = 0

        for path in paths:
            file_obj = save_upload(Path(path))
            if file_obj:
                job = queue.enqueue(
                    str(file_obj.path),
                    printer=self.printer_combo.currentText(),
                    copies=self.copies_spin.value(),
                    duplex=self.duplex_cb.isChecked(),
                    color=self.color_combo.currentText() == "彩色",
                    paper_size=self.paper_combo.currentText(),
                )
                self._tracking_job_ids.append(job.id)
                submitted += 1

        if submitted:
            self.tracking_label.setText(
                f"已提交 {submitted}/{total} 个任务，等待处理..."
            )
            self.tracking_label.setVisible(True)
            self.progress.setRange(0, 100)
            self.submit_btn.set_success()
        else:
            self.submit_btn.set_error()
            self.progress.setVisible(False)

    def on_job_status(self, data: dict):
        jid = data.get("job_id")
        if jid not in self._tracking_job_ids:
            return
        status = data.get("status", "")
        if status == "completed":
            self.tracking_label.setText(f"任务 #{jid} 完成")
        elif status == "failed":
            self.tracking_label.setText(f"任务 #{jid} 失败: {data.get('error', '')}")
        elif status == "printing":
            self.tracking_label.setText(f"任务 #{jid} 正在打印...")
