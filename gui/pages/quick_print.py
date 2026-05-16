"""Quick print page: file picker (drag/drop + click), multi-file, batch submit."""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from gui.components.drop_zone import DropZoneWidget
from gui.components.file_item import IMAGE_EXTS, collect_file_paths, populate_file_list
from gui.components.page_base import PageBase
from gui.components.printer_combo import PrinterComboBox
from gui.components.progress_state import ProgressState
from gui.components.stateful_button import StatefulButton
from gui.components.toggle_switch import LabeledToggle


class QuickPrintPage(PageBase):
    def __init__(self, main_window, parent=None):
        self._mw = main_window
        super().__init__(parent)
        self._file_paths: list[str] = []
        self._tracking_job_ids: list[int] = []

    def _build_content(self, layout: QVBoxLayout):
        title_row = QHBoxLayout()
        title_lbl = QLabel('快速打印')
        title_lbl.setObjectName('pageTitle')
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        self.clear_btn = QPushButton('✕ 清除')
        self.clear_btn.setObjectName('ghost')
        self.clear_btn.setToolTip('清除所有已选文件和结果，重新开始')
        self.clear_btn.clicked.connect(self._confirm_clear)
        title_row.addWidget(self.clear_btn)
        layout.addLayout(title_row)

        # Drop zone
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
        self.printer_combo = PrinterComboBox(self._mw._config)
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        cfg = self._mw._config
        self.copies_spin.setValue(cfg.get('default_copies', 1) if cfg else 1)
        self.duplex_cb = LabeledToggle(
            '双面', checked=cfg.get('default_duplex', False) if cfg else False, label_first=True
        )
        self.color_combo = QComboBox()
        self.color_combo.addItems(['彩色', '黑白'])
        default_color = cfg.get('default_color', True) if cfg else True
        self.color_combo.setCurrentText('彩色' if default_color else '黑白')
        self.paper_combo = QComboBox()
        self.paper_combo.addItems(['A4', 'Letter', 'A3'])
        if cfg:
            self.paper_combo.setCurrentText(cfg.get('paper_size', 'A4'))
        options_row.addWidget(QLabel('打印机:'))
        options_row.addWidget(self.printer_combo)
        options_row.addWidget(QLabel('份数:'))
        options_row.addWidget(self.copies_spin)
        options_row.addWidget(self.duplex_cb)
        options_row.addWidget(QLabel('颜色:'))
        options_row.addWidget(self.color_combo)
        options_row.addWidget(QLabel('纸张:'))
        options_row.addWidget(self.paper_combo)
        layout.addLayout(options_row)

        # Page range + N-up row
        adv_row = QHBoxLayout()
        self.page_range_input = QLineEdit()
        self.page_range_input.setPlaceholderText('全部')
        self.page_range_input.setToolTip('指定页码范围，如 1-3,5,7-9（留空=全部）')
        self.page_range_input.setMaximumWidth(120)
        self.nup_combo = QComboBox()
        self.nup_combo.addItems(['1 页/张', '2 页/张', '4 页/张', '6 页/张', '8 页/张', '16 页/张'])
        self.nup_combo.setToolTip('每张纸打印的页数')
        adv_row.addWidget(QLabel('页码范围:'))
        adv_row.addWidget(self.page_range_input)
        adv_row.addWidget(QLabel('多页合一:'))
        adv_row.addWidget(self.nup_combo)
        adv_row.addStretch()
        layout.addLayout(adv_row)

        self.drop_zone.setToolTip('支持 PDF、Office 文档、图片文件，可拖拽或多选')
        self.copies_spin.setToolTip('设置打印份数，最大不超过打印机支持上限')
        self.duplex_cb.setToolTip('开启后打印机将双面打印（需打印机支持）')

        # Progress
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self._progress = ProgressState(self.progress)
        self.progress.setVisible(False)
        self.progress.setRange(0, 100)
        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setObjectName('ghostDanger')
        self.cancel_btn.setProperty('compact', True)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_print)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.cancel_btn)
        layout.addLayout(progress_row)

        self.submit_btn = StatefulButton('开始打印')
        self.submit_btn.clicked.connect(self._submit)
        layout.addWidget(self.submit_btn)

        self.tracking_label = QLabel('')
        self.tracking_label.setVisible(False)
        self.tracking_label.setWordWrap(True)
        layout.addWidget(self.tracking_label)

        self.error_label = QLabel('')
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet('color: #C53A3A; font-size: 12px; padding: 8px 0;')
        layout.addWidget(self.error_label)

        QTimer.singleShot(300, lambda: self.printer_combo.refresh(self._mw._app.state))
        self.printer_combo.currentTextChanged.connect(self._on_printer_changed)

    def _on_printer_changed(self, name: str):
        if not name:
            return
        self.printer_combo.configure_copies(self.copies_spin)
        self.printer_combo.configure_color(self.color_combo)
        self.printer_combo.configure_duplex(self.duplex_cb)
        self.printer_combo.configure_paper(self.paper_combo)

    def _confirm_clear(self):
        from PySide6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            '确认清除',
            '确定要清除所有已选文件吗？此操作不可撤销。',
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
        self.cancel_btn.setVisible(False)
        self.tracking_label.setVisible(False)
        self.tracking_label.setText('')
        self.error_label.setVisible(False)
        self.error_label.setText('')
        self.submit_btn.reset()

    def _has_unsaved_content(self) -> bool:
        return self.file_list.count() > 0

    def _on_files_selected(self, paths: list[str]):
        self._file_paths = paths
        populate_file_list(self.file_list, paths, open_btn=True)

    def _get_current_paths(self) -> list[str]:
        return collect_file_paths(self.file_list)

    def _submit(self):
        paths = self._get_current_paths()
        if not paths:
            return

        # Check Quark API keys if any image files are included
        has_images = any(Path(p).suffix.lower() in IMAGE_EXTS for p in paths)
        if has_images:
            config = self._mw._config
            if config:
                key_id = config.get('quark_api_key_id', '')
                key_secret = config.get('quark_api_key', '')
                if not key_id or not key_secret:
                    self._show_quark_missing_dialog()
                    return

        self.submit_btn.set_loading()
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.error_label.setVisible(False)
        self._progress.set_indeterminate()
        self._tracking_job_ids.clear()

        queue = self._mw._app.state.job_queue
        config = self._mw._config
        total = len(paths)
        submitted = 0

        for path in paths:
            p = Path(path)
            try:
                file_bytes = p.read_bytes()
                from app.services.upload import handle_file_upload

                result = handle_file_upload(
                    p.name,
                    file_bytes,
                    config,
                    queue,
                    source='gui',
                    printer=self.printer_combo.currentText(),
                    copies=str(self.copies_spin.value()),
                    duplex='1' if self.duplex_cb.isChecked() else '0',
                    color='1' if self.color_combo.currentText() == '彩色' else '0',
                    paper_size=self.paper_combo.currentText(),
                    page_range=self.page_range_input.text().strip(),
                    nup=int(self.nup_combo.currentText().split(' ')[0]),
                )
                if result.success:
                    self._tracking_job_ids.append(result.job_id)
                    submitted += 1
                else:
                    logger.warning(f'文件上传失败: {p.name} - {result.error}')
            except Exception as e:
                logger.error(f'文件上传异常: {p.name} - {e}')

        if submitted:
            self.tracking_label.setText(f'已提交 {submitted}/{total} 个任务，等待处理...')
            self.tracking_label.setVisible(True)
            self.progress.setRange(0, 100)
            self.submit_btn.set_success()
            self.cancel_btn.setVisible(False)
        else:
            self.submit_btn.set_error()
            self.progress.setVisible(False)
            self.cancel_btn.setVisible(False)
            self.error_label.setText('文件上传失败，请检查文件是否存在或格式是否支持')
            self.error_label.setVisible(True)

    def _show_quark_missing_dialog(self):
        from PySide6.QtWidgets import QMessageBox, QPushButton

        msg = '夸克 API 未配置，图片打印需要 API 密钥。\n请在设置页面中配置「夸克 API Key ID」和「夸克 API Key」。'
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle('夸克 API 未配置')
        box.setText(msg)
        settings_btn = QPushButton('前往设置')
        box.addButton(settings_btn, QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is settings_btn:
            self._mw.sidebar.setCurrentRow(self._mw.NAV_ITEMS.index('设置'))

    def _cancel_print(self):
        if not self._tracking_job_ids:
            return
        queue = self._mw._app.state.job_queue
        for jid in self._tracking_job_ids:
            queue.cancel_job(jid)
        self._clear_all()

    def on_job_status(self, data: dict):
        jid = data.get('job_id')
        if jid not in self._tracking_job_ids:
            return
        status = data.get('status', '')
        if status == 'completed':
            self.tracking_label.setText(f'任务 #{jid} 完成')
        elif status == 'failed':
            self.tracking_label.setText(f'任务 #{jid} 失败: {data.get("error", "")}')
        elif status == 'printing':
            self.tracking_label.setText(f'任务 #{jid} 正在打印...')
