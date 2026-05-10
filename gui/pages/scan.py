"""Document scan page: image upload → Quark API enhancement → PDF/image output."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from gui.components.drop_zone import DropZoneWidget
from gui.components.stateful_button import StatefulButton
from gui.components.toggle_switch import LabeledToggle
from gui.components.printer_capabilities import query_capabilities

IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif", ".heic", ".heif"]


class _ScanResultItem(QWidget):
    """Custom widget for a scan result item with thumbnail preview."""

    def __init__(self, label: str, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 4, 8, 4)
        lo.setSpacing(10)

        thumb = QLabel()
        thumb.setFixedSize(48, 48)
        thumb.setPixmap(pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lo.addWidget(thumb)

        info = QLabel(label)
        info.setStyleSheet("font-size: 12px; color: #8A8178;")
        lo.addWidget(info, 1)


class ScanWorker(QThread):
    """Background worker for Quark API enhancement."""
    progress = Signal(int, int)  # current, total
    finished = Signal(int, list)  # job_id, list of (filepath, enhanced_bytes or None)
    error = Signal(str)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.paths = paths
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        from app.printing.enhancer import QuarkEnhancer
        from app.config import Config

        config = Config()
        enhancer = QuarkEnhancer(config)
        results: list[tuple[str, bytes | None]] = []

        for i, path in enumerate(self.paths):
            if self._cancelled:
                break
            self.progress.emit(i + 1, len(self.paths))
            try:
                enhanced = enhancer.enhance(path)
                results.append((path, enhanced))
            except Exception as e:
                results.append((path, None))

        self.finished.emit(len(self.paths), results)


class ScanPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._generated_images: list[bytes] = []
        self._generated_pdf: bytes | None = None

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

        title_row = QHBoxLayout()
        title_lbl = QLabel("文档扫描")
        title_lbl.setObjectName("pageTitle")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        self.clear_btn = QPushButton("✕ 清除")
        self.clear_btn.setObjectName("ghost")
        self.clear_btn.setToolTip("清除所有已选文件和结果，重新开始")
        self.clear_btn.clicked.connect(self._confirm_clear)
        title_row.addWidget(self.clear_btn)
        layout.addLayout(title_row)

        # Drop zone — images only
        self.drop_zone = DropZoneWidget(self, extensions=IMAGE_EXTS)
        self.drop_zone.setToolTip("支持 JPG、PNG、TIFF 等图片格式")
        self.drop_zone._icon_label.setText("🖼")
        self.drop_zone._text_label.setText("点击选择图片，或拖拽到此处")
        self.drop_zone.files_selected.connect(self._on_files_selected)
        layout.addWidget(self.drop_zone)

        # File list
        self.file_list = QListWidget()
        self.file_list.setVisible(False)
        self.file_list.setMinimumHeight(80)
        self.file_list.setMaximumHeight(200)
        layout.addWidget(self.file_list)

        # Options row
        options_row = QHBoxLayout()
        self.output_combo = QComboBox()
        self.output_combo.addItems(["PDF", "图片"])
        self.output_combo.setToolTip("选择输出为 PDF 文档或独立图片文件")
        self.output_combo.currentTextChanged.connect(self._on_output_format_changed)
        self.merge_cb = LabeledToggle("合并为一个文件", checked=False)
        self.merge_cb.setToolTip("多张图片合并为一个 PDF 文件")
        self.merge_cb.setVisible(False)
        options_row.addWidget(QLabel("输出格式:"))
        options_row.addWidget(self.output_combo)
        options_row.addWidget(self.merge_cb)
        layout.addLayout(options_row)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # Generate button
        self.generate_btn = StatefulButton("开始扫描")
        self.generate_btn.clicked.connect(self._generate)
        layout.addWidget(self.generate_btn)

        # Cancel button (hidden until generation starts)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("ghostDanger")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_generation)
        layout.addWidget(self.cancel_btn)

        # Result list
        self.result_list = QListWidget()
        self.result_list.setVisible(False)
        self.result_list.setMinimumHeight(100)
        self.result_list.setMaximumHeight(300)
        layout.addWidget(self.result_list)

        # Action buttons (post-generation)
        actions_row = QHBoxLayout()
        self.copy_btn = QPushButton("复制到剪贴板")
        self.copy_btn.setObjectName("ghost")
        self.copy_btn.clicked.connect(self._copy_result)
        self.export_btn = QPushButton("导出")
        self.export_btn.setObjectName("ghost")
        self.export_btn.clicked.connect(self._export_result)
        self.print_btn = QPushButton("打印")
        self.print_btn.setObjectName("primary")
        self.print_btn.clicked.connect(self._show_print_dialog)

        actions_row.addWidget(self.copy_btn)
        actions_row.addWidget(self.export_btn)
        actions_row.addWidget(self.print_btn)
        actions_row.addStretch()
        self._actions_widget = QWidget()
        self._actions_widget.setLayout(actions_row)
        self._actions_widget.setVisible(False)
        layout.addWidget(self._actions_widget)

        self._export_action_widget = QWidget()
        self._export_action_widget.setVisible(False)
        layout.addWidget(self._export_action_widget)

        # Print options (hidden until print clicked)
        self._print_panel = QWidget()
        self._print_panel.setVisible(False)
        print_lo = QHBoxLayout(self._print_panel)
        print_lo.setContentsMargins(0, 0, 0, 0)
        self._printer_combo = QComboBox()
        self._printer_combo.setPlaceholderText("选择打印机")
        self._copies_spin = QSpinBox()
        self._copies_spin.setRange(1, 99)
        self._copies_spin.setValue(1)
        self._copies_spin.setToolTip("设置打印份数，最大不超过打印机支持上限")
        self._duplex_cb = LabeledToggle("双面", checked=True)
        self._duplex_cb.setToolTip("开启后打印机将双面打印（需打印机支持）")
        self._color_cb = LabeledToggle("彩色", checked=True)
        self._paper_combo = QComboBox()
        self._paper_combo.addItems(["A4", "Letter", "A3"])
        print_lo.addWidget(QLabel("打印机:"))
        print_lo.addWidget(self._printer_combo)
        print_lo.addWidget(QLabel("份数:"))
        print_lo.addWidget(self._copies_spin)
        print_lo.addWidget(self._duplex_cb)
        print_lo.addWidget(self._color_cb)
        print_lo.addWidget(QLabel("纸张:"))
        print_lo.addWidget(self._paper_combo)
        submit_print_btn = QPushButton("确认打印")
        submit_print_btn.setObjectName("primary")
        submit_print_btn.clicked.connect(self._do_print)
        print_lo.addWidget(submit_print_btn)
        layout.addWidget(self._print_panel)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        layout.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        self._file_paths: list[str] = []
        self._worker: ScanWorker | None = None
        self._cancelled_by_user = False

        QTimer.singleShot(300, self._refresh_printers)
        self._printer_combo.currentTextChanged.connect(self._on_printer_changed)

    def _refresh_printers(self):
        monitor = getattr(self._mw._app.state, "printer_monitor", None)
        if monitor is None:
            return
        self._printer_combo.clear()
        raw = monitor.get_all_statuses()
        for name in raw:
            self._printer_combo.addItem(name)

        # Auto-select default
        try:
            import win32print
            default = win32print.GetDefaultPrinter()
            idx = self._printer_combo.findText(default)
            if idx >= 0:
                self._printer_combo.setCurrentIndex(idx)
        except Exception:
            pass

    def _on_printer_changed(self, name: str):
        if not name:
            return
        caps = query_capabilities(name)
        self._copies_spin.setRange(1, caps.copies_max)
        self._copies_spin.setToolTip(f"最大复印数: {caps.copies_max}")

    def _confirm_clear(self):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "确认清除", "确定要清除所有已选文件和结果吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_all()

    def _clear_all(self):
        self._file_paths.clear()
        self.file_list.clear()
        self.file_list.setVisible(False)
        self._clear_results()
        self.progress.setVisible(False)
        self._status_label.setText("")
        self.cancel_btn.setVisible(False)
        self.generate_btn.setVisible(True)
        self.generate_btn.reset()
        self._export_action_widget.setVisible(False)

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
        self._update_merge_visibility()
        self._clear_results()

    def _on_output_format_changed(self, fmt: str):
        self._update_merge_visibility()

    def _update_merge_visibility(self):
        multi = len(self._get_current_paths()) > 1
        pdf_mode = self.output_combo.currentText() == "PDF"
        self.merge_cb.setVisible(multi and pdf_mode)

    def _get_current_paths(self) -> list[str]:
        paths = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            w = self.file_list.itemWidget(item)
            if w and hasattr(w, "file_path"):
                paths.append(w.file_path)
        return paths

    def _clear_results(self):
        self.result_list.setVisible(False)
        self._actions_widget.setVisible(False)
        self._print_panel.setVisible(False)
        self._generated_images = []
        self._generated_pdf = None

    def _generate(self):
        paths = self._get_current_paths()
        if not paths:
            return
        self.generate_btn.set_loading()
        self.generate_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self._cancelled_by_user = False
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.result_list.clear()
        self.result_list.setVisible(False)
        self._actions_widget.setVisible(False)
        self._print_panel.setVisible(False)
        self._generated_images = []
        self._generated_pdf = None
        self._status_label.setText("")

        self._worker = ScanWorker(paths)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _cancel_generation(self):
        if self._worker:
            self._worker.cancel()
        self._cancelled_by_user = True
        self._reset_after_cancel()

    def _reset_after_cancel(self):
        self.cancel_btn.setVisible(False)
        self.generate_btn.setVisible(True)
        self.generate_btn.reset()
        self.progress.setVisible(False)
        self._status_label.setText("已取消")
        self._status_label.setStyleSheet("")

    def _on_scan_progress(self, current: int, total: int):
        self.progress.setRange(0, total)
        self.progress.setValue(current)

    def _on_scan_finished(self, total: int, results: list[tuple[str, bytes | None]]):
        # Ignore results if user cancelled
        if self._cancelled_by_user:
            return
        self.cancel_btn.setVisible(False)
        self.generate_btn.setVisible(True)
        self.progress.setRange(0, 100)
        self.generate_btn.set_success()

        # Collect enhanced images
        enhanced_images: list[bytes] = []
        errors = 0
        for path, data in results:
            if data:
                enhanced_images.append(data)
            else:
                errors += 1

        if not enhanced_images:
            self._status_label.setText("扫描失败，请检查 Quark API 配置")
            self._status_label.setStyleSheet("color: #C53A3A;")
            self.generate_btn.set_error()
            return

        # Generate output
        output_format = self.output_combo.currentText()
        merge = self.merge_cb.isChecked() and output_format == "PDF"

        try:
            if output_format == "PDF":
                self._generate_pdf(enhanced_images, merge)
            else:
                self._generate_images(enhanced_images, merge)
        except Exception as e:
            self._status_label.setText(f"生成失败: {e}")
            self._status_label.setStyleSheet("color: #C53A3A;")
            self.generate_btn.set_error()
            return

        status_parts = [f"成功处理 {len(enhanced_images)}/{total} 张图片"]
        if errors:
            status_parts.append(f"{errors} 张失败")
        self._status_label.setText("，".join(status_parts))
        self._status_label.setStyleSheet("color: #6B8F6B;")
        self._actions_widget.setVisible(True)

    def _generate_pdf(self, images: list[bytes], merge: bool):
        if merge:
            # Single PDF with all pages
            pil_images = [Image.open(io.BytesIO(img)).convert("RGB") for img in images]
            buf = io.BytesIO()
            pil_images[0].save(buf, "PDF", save_all=True, append_images=pil_images[1:])
            self._generated_pdf = buf.getvalue()
            self.result_list.clear()
            item = QListWidgetItem()
            w = _ScanResultItem(f"合并 PDF — {len(images)} 页", _make_thumbnail(images[0]))
            item.setSizeHint(w.sizeHint())
            self.result_list.addItem(item)
            self.result_list.setItemWidget(item, w)
        else:
            # Separate PDFs
            self._generated_images = images
            self.result_list.clear()
            for i, img_data in enumerate(images):
                pil_img = Image.open(io.BytesIO(img_data)).convert("RGB")
                buf = io.BytesIO()
                pil_img.save(buf, "PDF")
                self._generated_images[i] = buf.getvalue()
                item = QListWidgetItem()
                w = _ScanResultItem(f"文档 {i+1}.pdf", _make_thumbnail(img_data))
                item.setSizeHint(w.sizeHint())
                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, w)
        self.result_list.setVisible(True)

    def _generate_images(self, images: list[bytes], merge: bool):
        if merge:
            # Merge into a single multi-page TIFF
            pil_images = [Image.open(io.BytesIO(img)).convert("RGB") for img in images]
            buf = io.BytesIO()
            pil_images[0].save(buf, "TIFF", save_all=True, append_images=pil_images[1:])
            self._generated_images = [buf.getvalue()]
            self.result_list.clear()
            item = QListWidgetItem()
            w = _ScanResultItem(f"合并 TIFF — {len(images)} 页", _make_thumbnail(images[0]))
            item.setSizeHint(w.sizeHint())
            self.result_list.addItem(item)
            self.result_list.setItemWidget(item, w)
        else:
            self._generated_images = images
            self.result_list.clear()
            for i, img_data in enumerate(images):
                item = QListWidgetItem()
                w = _ScanResultItem(f"文档 {i+1}.jpg", _make_thumbnail(img_data))
                item.setSizeHint(w.sizeHint())
                self.result_list.addItem(item)
                self.result_list.setItemWidget(item, w)
        self.result_list.setVisible(True)

    def _on_scan_error(self, msg: str):
        self._status_label.setText(msg)
        self._status_label.setStyleSheet("color: #C53A3A;")
        self.cancel_btn.setVisible(False)
        self.generate_btn.setVisible(True)
        self.generate_btn.set_error()
        self.progress.setVisible(False)

    def _copy_result(self):
        if self._generated_pdf:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtCore import QMimeData
            mime = QMimeData()
            mime.setData("application/pdf", self._generated_pdf)
            QGuiApplication.clipboard().setMimeData(mime)
            self._status_label.setText("PDF 已复制到剪贴板")
        elif self._generated_images:
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtCore import QMimeData
            mime = QMimeData()
            if len(self._generated_images) == 1:
                pixmap = QPixmap()
                pixmap.loadFromData(self._generated_images[0])
                QGuiApplication.clipboard().setPixmap(pixmap)
            else:
                # Can't copy multiple images natively, copy first as image
                pixmap = QPixmap()
                pixmap.loadFromData(self._generated_images[0])
                QGuiApplication.clipboard().setPixmap(pixmap)
                self._status_label.setText(f"已复制第 1 张图片（共 {len(self._generated_images)} 张）")
                return
            self._status_label.setText("图片已复制到剪贴板")
        self._status_label.setStyleSheet("color: #6B8F6B;")

    def _export_result(self):
        ext = ".pdf" if self._generated_pdf else ".jpg"
        filter_str = "PDF (*.pdf)" if self._generated_pdf else "JPEG (*.jpg);;PNG (*.png)"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出文件", f"scan_result{ext}", filter_str,
        )
        if not file_path:
            return

        try:
            out = Path(file_path)
            if self._generated_pdf:
                out.write_bytes(self._generated_pdf)
            elif self._generated_images:
                data = self._generated_images[0] if len(self._generated_images) == 1 else None
                if data:
                    out.write_bytes(data)
                else:
                    out.write_bytes(self._generated_images[0])
            self._show_export_result(out)
        except Exception as e:
            self._status_label.setText(f"导出失败: {e}")
            self._status_label.setStyleSheet("color: #C53A3A;")

    def _show_export_result(self, path: Path):
        self._status_label.setText(f"已导出: {path}")
        self._status_label.setStyleSheet("color: #6B8F6B;")

        # Show action buttons
        from PySide6.QtWidgets import QPushButton
        import subprocess
        # Remove old buttons if any
        for btn in self._export_action_widget.findChildren(QPushButton):
            btn.deleteLater()

        open_btn = QPushButton("打开文件")
        open_btn.clicked.connect(lambda: subprocess.Popen(["explorer", str(path)], shell=True))
        open_folder_btn = QPushButton("打开所在文件夹")
        open_folder_btn.clicked.connect(
            lambda: subprocess.Popen(["explorer", "/select,", str(path)], shell=True)
        )

        lo = self._export_action_widget.layout() or QHBoxLayout(self._export_action_widget)
        lo.addWidget(open_btn)
        lo.addWidget(open_folder_btn)
        self._export_action_widget.setVisible(True)

    def _show_print_dialog(self):
        if not (self._generated_pdf or self._generated_images):
            return

        monitor = getattr(self._mw._app.state, "printer_monitor", None)
        printers = list(monitor.get_all_statuses().keys()) if monitor else []

        from gui.components.print_dialog import PrintDialog
        dlg = PrintDialog(printers, self)
        if dlg.exec() == PrintDialog.DialogCode.Accepted:
            params = dlg.get_result()
            if params:
                self._do_print(params)

    def _do_print(self, params: dict | None = None):
        if not (self._generated_pdf or self._generated_images):
            return
        try:
            import tempfile
            from app.printing.job_queue import get_queue

            queue = get_queue()
            data_list = [self._generated_pdf] if self._generated_pdf else self._generated_images
            ext = ".pdf" if self._generated_pdf else ".jpg"

            printer = params.get("printer", "") if params else self._printer_combo.currentText()
            copies = params.get("copies", 1) if params else self._copies_spin.value()
            duplex = params.get("duplex", True) if params else self._duplex_cb.isChecked()
            color = params.get("color", True) if params else self._color_cb.isChecked()
            paper_size = params.get("paper_size", "A4") if params else self._paper_combo.currentText()

            submitted = 0
            for data in data_list:
                with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as f:
                    f.write(data)
                    tmp_path = f.name
                job = queue.enqueue(
                    tmp_path,
                    printer=printer,
                    copies=copies,
                    duplex=duplex,
                    color=color,
                    paper_size=paper_size,
                )
                submitted += 1

            self._status_label.setText(f"已提交 {submitted} 个打印任务")
            self._status_label.setStyleSheet("color: #6B8F6B;")
        except Exception as e:
            self._status_label.setText(f"打印失败: {e}")
            self._status_label.setStyleSheet("color: #C53A3A;")

    def on_job_status(self, data: dict):
        pass  # Could show notifications for print jobs from this page


class _FileItemWidget(QWidget):
    """Custom widget for a file list item with thumbnail, path, and delete button."""

    def __init__(self, file_path: str, list_widget: QListWidget, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._list_widget = list_widget
        self.setMinimumHeight(48)
        p = Path(file_path)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 4, 8, 4)
        lo.setSpacing(10)

        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if p.suffix.lower() in IMAGE_EXTS:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText("🖼")
        else:
            thumb.setText("📄")
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

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(28)
        del_btn.setObjectName("ghostDanger")
        del_btn.setProperty("compact", True)
        del_btn.clicked.connect(self._delete_self)
        lo.addWidget(del_btn)

    def _delete_self(self):
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            w = self._list_widget.itemWidget(item)
            if w is self:
                self._list_widget.takeItem(i)
                break


def _make_thumbnail(img_data: bytes, size: int = 48) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(img_data)
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)