"""Document scan page: image upload → Quark API enhancement → PDF/image output."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.components.drop_zone import DropZoneWidget
from gui.components.file_item import IMAGE_EXTS, collect_file_paths, populate_file_list
from gui.components.page_base import PageBase
from gui.components.printer_combo import PrinterComboBox
from gui.components.stateful_button import StatefulButton
from gui.components.toggle_switch import LabeledToggle
from gui.pages.scan_worker import ScanWorker


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
        info.setStyleSheet('font-size: 12px; color: #8A8178;')
        lo.addWidget(info, 1)


class ScanPage(PageBase):
    def __init__(self, main_window, parent=None):
        self._mw = main_window
        super().__init__(parent)
        self._generated_images: list[bytes] = []
        self._generated_pdf: bytes | None = None
        self._file_paths: list[str] = []
        self._worker: ScanWorker | None = None
        self._cancelled_by_user = False

    def _build_content(self, layout: QVBoxLayout):
        title_row = QHBoxLayout()
        title_lbl = QLabel('文档扫描')
        title_lbl.setObjectName('pageTitle')
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        self.clear_btn = QPushButton('✕ 清除')
        self.clear_btn.setObjectName('ghost')
        self.clear_btn.setToolTip('清除所有已选文件和结果，重新开始')
        self.clear_btn.clicked.connect(self._confirm_clear)
        title_row.addWidget(self.clear_btn)
        layout.addLayout(title_row)

        # Drop zone — images only
        self.drop_zone = DropZoneWidget(self, extensions=IMAGE_EXTS)
        self.drop_zone.setToolTip('支持 JPG、PNG、TIFF 等图片格式')
        self.drop_zone._icon_label.setText('\U0001f5bc')
        self.drop_zone._text_label.setText('点击选择图片，或拖拽到此处')
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
        self.output_combo.addItems(['PDF', '图片'])
        self.output_combo.setToolTip('选择输出为 PDF 文档或独立图片文件')
        self.output_combo.currentTextChanged.connect(self._on_output_format_changed)
        self.merge_cb = LabeledToggle('合并为一个文件', checked=False, label_first=True)
        self.merge_cb.setToolTip('多张图片合并为一个 PDF 文件')
        self.merge_cb.setVisible(False)
        options_row.addWidget(QLabel('输出格式:'))
        options_row.addWidget(self.output_combo)
        options_row.addWidget(self.merge_cb)
        layout.addLayout(options_row)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        self.generate_btn = StatefulButton('开始扫描')
        self.generate_btn.clicked.connect(self._generate)
        layout.addWidget(self.generate_btn)

        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setObjectName('ghostDanger')
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
        self.copy_btn = QPushButton('复制到剪贴板')
        self.copy_btn.setObjectName('ghost')
        self.copy_btn.clicked.connect(self._copy_result)
        self.export_btn = QPushButton('导出')
        self.export_btn.setObjectName('ghost')
        self.export_btn.clicked.connect(self._export_result)
        self.print_btn = QPushButton('打印')
        self.print_btn.setObjectName('primary')
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
        self._export_actions_layout = QHBoxLayout(self._export_action_widget)
        self._export_actions_layout.setContentsMargins(0, 0, 0, 0)
        self._export_action_widget.setVisible(False)
        layout.addWidget(self._export_action_widget)

        # Print panel
        self._print_panel = QWidget()
        self._print_panel.setVisible(False)
        print_lo = QHBoxLayout(self._print_panel)
        print_lo.setContentsMargins(0, 0, 0, 0)
        self._printer_combo = PrinterComboBox(self._mw._config)
        self._copies_spin = QSpinBox()
        self._copies_spin.setRange(1, 99)
        cfg = self._mw._config
        self._copies_spin.setValue(cfg.get('default_copies', 1) if cfg else 1)
        self._duplex_cb = LabeledToggle(
            '双面', checked=cfg.get('default_duplex', False) if cfg else False, label_first=True
        )
        self._color_combo = QComboBox()
        self._color_combo.addItems(['彩色', '黑白'])
        if cfg:
            self._color_combo.setCurrentText('彩色' if cfg.get('default_color', True) else '黑白')
        self._paper_combo = QComboBox()
        self._paper_combo.addItems(['A4', 'Letter', 'A3'])
        if cfg:
            self._paper_combo.setCurrentText(cfg.get('paper_size', 'A4'))
        print_lo.addWidget(QLabel('打印机:'))
        print_lo.addWidget(self._printer_combo)
        print_lo.addWidget(QLabel('份数:'))
        print_lo.addWidget(self._copies_spin)
        print_lo.addWidget(self._duplex_cb)
        print_lo.addWidget(QLabel('颜色:'))
        print_lo.addWidget(self._color_combo)
        print_lo.addWidget(QLabel('纸张:'))
        print_lo.addWidget(self._paper_combo)
        submit_print_btn = QPushButton('确认打印')
        submit_print_btn.setObjectName('primary')
        submit_print_btn.clicked.connect(self._do_print)
        print_lo.addWidget(submit_print_btn)
        layout.addWidget(self._print_panel)

        self._status_label = QLabel('')
        layout.addWidget(self._status_label)

        QTimer.singleShot(300, lambda: self._printer_combo.refresh(self._mw._app.state))
        self._printer_combo.currentTextChanged.connect(self._on_printer_changed)

    def _on_printer_changed(self, name: str):
        if not name:
            return
        self._printer_combo.configure_copies(self._copies_spin)
        self._printer_combo.configure_color(self._color_combo)
        self._printer_combo.configure_duplex(self._duplex_cb)
        self._printer_combo.configure_paper(self._paper_combo)

    def _on_files_selected(self, paths: list[str]):
        self._file_paths = paths
        populate_file_list(self.file_list, paths)
        self.file_list.setVisible(len(paths) > 0)

    def _confirm_clear(self):
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            '确认清除',
            '确定要清除所有已选文件和结果吗？此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._clear_all()

    def _clear_all(self):
        self._file_paths.clear()
        self.file_list.clear()
        self.file_list.setVisible(False)
        self.result_list.clear()
        self.result_list.setVisible(False)
        self._actions_widget.setVisible(False)
        self._export_action_widget.setVisible(False)
        self._print_panel.setVisible(False)
        self._status_label.setText('')
        self._generated_images.clear()
        self._generated_pdf = None
        self.progress.setVisible(False)
        self.generate_btn.reset()
        self.generate_btn.setEnabled(True)
        self.copy_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.print_btn.setEnabled(True)

    def _has_unsaved_content(self) -> bool:
        return self.file_list.count() > 0

    def _on_output_format_changed(self, fmt: str):
        self.merge_cb.setVisible(fmt == 'PDF')

    def _generate(self):
        paths = collect_file_paths(self.file_list)
        if not paths:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, '提示', '请先选择需要扫描的图片')
            return
        self._cancelled_by_user = False
        self.generate_btn.set_loading()
        self.cancel_btn.setVisible(True)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self._status_label.setText('正在处理...')
        self._status_label.setStyleSheet('')
        self._generated_images.clear()
        self._generated_pdf = None

        self._worker = ScanWorker(paths)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.finished.connect(self._on_generation_done)
        self._worker.error.connect(self._on_generation_error)
        self._worker.start()

    def _on_generation_done(self, images: list[bytes]):
        self._worker = None
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        if self._cancelled_by_user:
            return
        self._generated_images = images
        self._generated_pdf = None

        self.generate_btn.set_success()
        self._actions_widget.setVisible(True)
        self.result_list.clear()

        for i, img in enumerate(images):
            pixmap = QPixmap()
            pixmap.loadFromData(img)
            name = f'输出图片 {i + 1} ({len(img) / 1024:.0f} KB)'
            w = _ScanResultItem(name, pixmap)
            item = QListWidgetItem()
            item.setSizeHint(w.sizeHint())
            self.result_list.addItem(item)
            self.result_list.setItemWidget(item, w)
        self.result_list.setVisible(True)
        self._status_label.setText('')

    def _on_generation_error(self, msg: str):
        self._worker = None
        self.cancel_btn.setVisible(False)
        self.progress.setVisible(False)
        self.generate_btn.set_error()
        self._status_label.setText(f'扫描失败: {msg}')
        self._status_label.setStyleSheet('color: #C53A3A;')

    def _cancel_generation(self):
        if self._worker:
            self._cancelled_by_user = True
            self._worker.cancel()
            self._worker = None
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.generate_btn.reset()

    def _copy_result(self):
        if self._generated_pdf:
            data = self._generated_pdf
        elif self._generated_images:
            data = self._generated_images[0]
        else:
            return
        from PySide6.QtGui import QGuiApplication

        qapp = QGuiApplication.instance()
        if qapp:
            from PySide6.QtCore import QMimeData

            mime = QMimeData()
            mime.setData('application/octet-stream', data)
            qapp.clipboard().setMimeData(mime)
            self._status_label.setText('已复制到剪贴板')
            self._status_label.setStyleSheet('color: #6B8F6B;')

    def _export_result(self):

        ext = '.pdf' if self._generated_pdf else '.png'
        filter_str = 'PDF (*.pdf)' if self._generated_pdf else 'PNG (*.png)'
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            '导出扫描结果',
            f'scan_result{ext}',
            filter_str,
        )
        if not file_path:
            return

        try:
            out = Path(file_path)
            if self._generated_pdf:
                out.write_bytes(self._generated_pdf)
            elif self._generated_images:
                data = self._generated_images[0]
                out.write_bytes(data)
            self._show_export_result(out)
        except Exception as e:
            self._status_label.setText(f'导出失败: {e}')
            self._status_label.setStyleSheet('color: #C53A3A;')

    def _show_export_result(self, path: Path):
        self._status_label.setText(f'已导出: {path}')
        self._status_label.setStyleSheet('color: #6B8F6B;')
        self._export_action_widget.setVisible(True)

        # 清空并重用已有布局，避免重复创建 QHBoxLayout
        lo = self._export_actions_layout
        while lo.count():
            item = lo.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        open_btn = QPushButton('打开文件')
        open_btn.setObjectName('ghost')
        open_btn.setProperty('compact', True)
        open_btn.clicked.connect(lambda: self._open_export(path))
        folder_btn = QPushButton('打开文件夹')
        folder_btn.setObjectName('ghost')
        folder_btn.setProperty('compact', True)
        folder_btn.clicked.connect(lambda: self._open_export_folder(path))
        lo.addWidget(open_btn)
        lo.addWidget(folder_btn)
        lo.addStretch()

    def _open_export(self, path: Path):
        import subprocess

        subprocess.Popen(['explorer', str(path)], shell=True)

    def _open_export_folder(self, path: Path):
        import subprocess

        subprocess.Popen(['explorer', '/select,', str(path)], shell=True)

    def _show_print_dialog(self):
        from gui.components.print_dialog import PrintDialog

        monitor = getattr(self._mw._app.state, 'printer_monitor', None)
        printers = list(monitor.get_all_statuses()) if monitor else []
        dlg = PrintDialog(printers, self, config=self._mw._config)
        if dlg.exec() == PrintDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                self._printer_combo.setCurrentText(result['printer'])
                self._copies_spin.setValue(result['copies'])
                self._color_combo.setCurrentText('彩色' if result['color'] else '黑白')
                self._duplex_cb.setChecked(result['duplex'])
                self._paper_combo.setCurrentText(result['paper_size'])
                self._print_panel.setVisible(True)
                self._do_print()

    def _do_print(self):
        if not self._generated_pdf and not self._generated_images:
            return
        data = self._generated_pdf if self._generated_pdf else self._generated_images[0]
        ext = '.pdf' if self._generated_pdf else '.png'
        filename = f'scan_export{ext}'
        from app.services.upload import handle_file_upload

        queue = self._mw._app.state.job_queue
        config = self._mw._config
        result = handle_file_upload(
            filename,
            data,
            config,
            queue,
            source='gui',
            printer=self._printer_combo.currentText(),
            copies=str(self._copies_spin.value()),
            duplex='1' if self._duplex_cb.isChecked() else '0',
            color='1' if self._color_combo.currentText() == '彩色' else '0',
            paper_size=self._paper_combo.currentText(),
        )
        if result.success:
            self._status_label.setText('打印任务已提交')
            self._status_label.setStyleSheet('color: #6B8F6B;')
        else:
            self._status_label.setText(f'打印提交失败: {result.error}')
            self._status_label.setStyleSheet('color: #C53A3A;')
