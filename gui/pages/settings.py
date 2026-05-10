"""Settings page with 7 config groups."""

from __future__ import annotations

import secrets

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui.components.skeleton import SkeletonWidget
from gui.components.stateful_button import StatefulButton
from gui.components.toggle_switch import LabeledToggle
from gui.components.validators import PortValidator


class SettingsPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._config = getattr(main_window, '_config', None)
        self._changed_keys: set[str] = set()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName('dashboardScroll')
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 28, 32, 28)

        title_lbl = QLabel('设置')
        title_lbl.setObjectName('pageTitle')
        layout.addWidget(title_lbl)

        # Skeleton loading overlay (shown briefly on init for smooth perceived loading)
        self._skeleton = self._build_skeleton()
        layout.addWidget(self._skeleton)

        # Real form content — hidden until skeleton pulse completes
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._content)
        self._content.setVisible(False)

        # Group 1: Security
        security_group = QGroupBox('安全')
        security_form = QFormLayout(security_group)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        # Eye toggle for API key
        self._key_visible = False
        self.eye_btn = QPushButton('👁')
        self.eye_btn.setFixedWidth(32)
        self.eye_btn.setObjectName('ghost')
        self.eye_btn.setProperty('compact', True)
        self.eye_btn.clicked.connect(self._toggle_key_visibility)
        self.genkey_btn = QPushButton('🎲')
        self.genkey_btn.setFixedWidth(32)
        self.genkey_btn.setObjectName('ghost')
        self.genkey_btn.setProperty('compact', True)
        self.genkey_btn.setToolTip('随机生成 API Key')
        self.genkey_btn.clicked.connect(self._generate_key)
        key_row = QHBoxLayout()
        key_row.setSpacing(4)
        key_row.addWidget(self.api_key_input, 1)
        key_row.addWidget(self.eye_btn)
        key_row.addWidget(self.genkey_btn)
        key_widget = QWidget()
        key_widget.setLayout(key_row)
        security_form.addRow('API Key:', key_widget)
        self._content_layout.addWidget(security_group)

        # Group 1.5: Quark API
        quark_group = QGroupBox('夸克扫描 API')
        quark_form = QFormLayout(quark_group)
        self.quark_key_id_input = QLineEdit()
        quark_form.addRow('Key ID:', self.quark_key_id_input)
        self.quark_key_input = QLineEdit()
        self.quark_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._quark_key_visible = False
        self.quark_eye_btn = QPushButton('👁')
        self.quark_eye_btn.setFixedWidth(32)
        self.quark_eye_btn.setObjectName('ghost')
        self.quark_eye_btn.setProperty('compact', True)
        self.quark_eye_btn.clicked.connect(self._toggle_quark_key_visibility)
        quark_key_row = QHBoxLayout()
        quark_key_row.setSpacing(4)
        quark_key_row.addWidget(self.quark_key_input, 1)
        quark_key_row.addWidget(self.quark_eye_btn)
        quark_key_widget = QWidget()
        quark_key_widget.setLayout(quark_key_row)
        quark_form.addRow('API Key:', quark_key_widget)
        self._content_layout.addWidget(quark_group)

        # Group 2: Server
        server_group = QGroupBox('服务器')
        server_form = QFormLayout(server_group)
        self.port_input = QLineEdit()
        self.port_input.setValidator(PortValidator(self))
        server_form.addRow('端口:', self.port_input)
        self.ssl_cb = LabeledToggle('启用 SSL', checked=True)
        server_form.addRow('', self.ssl_cb)
        self._content_layout.addWidget(server_group)

        # Group 3: Printer
        printer_group = QGroupBox('打印机')
        printer_form = QFormLayout(printer_group)
        self.default_printer_combo = QComboBox()
        printer_form.addRow('默认打印机:', self.default_printer_combo)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(30, 3600)
        self.timeout_spin.setSuffix(' 秒')
        printer_form.addRow('打印超时:', self.timeout_spin)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        printer_form.addRow('重试次数:', self.retry_spin)
        self._content_layout.addWidget(printer_group)

        # Group 4: Notification
        notif_group = QGroupBox('通知')
        notif_form = QFormLayout(notif_group)
        self.notify_channel_combo = QComboBox()
        self.notify_channel_combo.addItems(['disabled', 'dingtalk', 'bark'])
        notif_form.addRow('通知渠道:', self.notify_channel_combo)
        self.webhook_input = QLineEdit()
        notif_form.addRow('Webhook / Key:', self.webhook_input)
        self.test_notify_btn = StatefulButton('测试通知')
        notif_form.addRow('', self.test_notify_btn)
        self._content_layout.addWidget(notif_group)

        # Group 5: Print Options
        print_opts_group = QGroupBox('打印选项')
        print_opts_form = QFormLayout(print_opts_group)
        self.default_copies_spin = QSpinBox()
        self.default_copies_spin.setRange(1, 99)
        print_opts_form.addRow('默认份数:', self.default_copies_spin)
        self.default_duplex_cb = LabeledToggle('双面')
        print_opts_form.addRow('', self.default_duplex_cb)
        self.default_color_cb = LabeledToggle('彩色')
        print_opts_form.addRow('', self.default_color_cb)
        self.paper_size_combo = QComboBox()
        self.paper_size_combo.addItems(['A4', 'Letter', 'A3'])
        print_opts_form.addRow('默认纸张:', self.paper_size_combo)
        self._content_layout.addWidget(print_opts_group)

        # Group 6: Worker
        worker_group = QGroupBox('Worker')
        worker_form = QFormLayout(worker_group)
        self.worker_count_spin = QSpinBox()
        self.worker_count_spin.setRange(1, 16)
        worker_form.addRow('工作进程数:', self.worker_count_spin)
        self.max_file_size_spin = QSpinBox()
        self.max_file_size_spin.setRange(1, 500)
        self.max_file_size_spin.setSuffix(' MB')
        worker_form.addRow('最大文件大小:', self.max_file_size_spin)
        self.print_dpi_spin = QSpinBox()
        self.print_dpi_spin.setRange(72, 1200)
        self.print_dpi_spin.setSuffix(' DPI')
        worker_form.addRow('打印 DPI:', self.print_dpi_spin)
        self.word_timeout_spin = QSpinBox()
        self.word_timeout_spin.setRange(30, 600)
        self.word_timeout_spin.setSuffix(' 秒')
        worker_form.addRow('Word 超时:', self.word_timeout_spin)
        self._content_layout.addWidget(worker_group)

        # Group 7: Logging
        log_group = QGroupBox('日志')
        log_form = QFormLayout(log_group)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(['DEBUG', 'INFO', 'WARNING', 'ERROR'])
        log_form.addRow('日志级别:', self.log_level_combo)
        self.log_max_days_spin = QSpinBox()
        self.log_max_days_spin.setRange(1, 365)
        log_form.addRow('日志保留天数:', self.log_max_days_spin)
        self._content_layout.addWidget(log_group)

        # Save button
        self.save_btn = StatefulButton('保存设置')
        self.save_btn.clicked.connect(self._save)
        self._content_layout.addWidget(self.save_btn)

        # Status label
        self.status_label = QLabel('')
        self._content_layout.addWidget(self.status_label)

        # Restart required label
        self.restart_label = QLabel('部分设置需要重启服务器才能生效')
        self.restart_label.setVisible(False)
        self.restart_label.setStyleSheet('color: #B8956A; font-size: 12px; padding: 4px 0;')
        self._content_layout.addWidget(self.restart_label)

        self._content_layout.addStretch()
        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

        self._load_config()
        self._setup_validation()
        self._populate_printers()
        self.test_notify_btn.clicked.connect(self._test_notification)
        self._mw._app.state.event_bus.on('printer_list_updated', self._populate_printers)

        # Brief skeleton pulse before revealing the form
        QTimer.singleShot(200, self._show_content)

    def _build_skeleton(self):
        """Build the skeleton loading placeholder mimicking form layout."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        # 10 rows of varying widths to simulate form fields
        for w in [280, 200, 350, 220, 300, 260, 340, 200, 250, 320]:
            sk = SkeletonWidget(width=w, height=24)
            layout.addWidget(sk, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return widget

    def _show_content(self):
        """Hide skeleton, reveal real form content."""
        self._skeleton.setVisible(False)
        self._content.setVisible(True)

    def _generate_key(self):
        self.api_key_input.setText(secrets.token_hex(32))
        self._key_visible = True
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Normal)
        self.eye_btn.setText('🙈')

    def _toggle_key_visibility(self):
        self._key_visible = not self._key_visible
        self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if self._key_visible else QLineEdit.EchoMode.Password
        )
        self.eye_btn.setText('🙈' if self._key_visible else '👁')

    def _toggle_quark_key_visibility(self):
        self._quark_key_visible = not self._quark_key_visible
        self.quark_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if self._quark_key_visible else QLineEdit.EchoMode.Password
        )
        self.quark_eye_btn.setText('🙈' if self._quark_key_visible else '👁')

    def _setup_validation(self):
        """Bind validation feedback to port input."""
        self.port_input.textChanged.connect(self._validate_port)

    def _validate_port(self):
        text = self.port_input.text()
        validator = self.port_input.validator()
        if not validator:
            return
        state, _, _ = validator.validate(text, len(text))
        if state == QValidator.State.Acceptable:
            self.port_input.setStyleSheet('border-color: #6B8F6B; border-width: 2px;')
            self.port_input.setToolTip('')
        elif state == QValidator.State.Intermediate:
            self.port_input.setStyleSheet('border-color: #B8956A; border-width: 2px;')
            self.port_input.setToolTip('端口号范围: 1024-65535')
        else:
            self.port_input.setStyleSheet('border-color: #C53A3A; border-width: 2px;')
            self.port_input.setToolTip('无效端口号')

    def _load_config(self):
        if not self._config:
            return
        c = self._config
        self.api_key_input.setText(c.get('api_key', ''))
        self.port_input.setText(str(c.get('port', 5000)))
        self.quark_key_id_input.setText(c.get('quark_api_key_id', ''))
        self.quark_key_input.setText(c.get('quark_api_key', ''))
        self.ssl_cb.setChecked(c.get('ssl_enabled', True))
        self.timeout_spin.setValue(c.get('job_timeout', 300))
        self.retry_spin.setValue(c.get('auto_retry_count', 0))
        self.notify_channel_combo.setCurrentText(c.get('notify_channel', 'disabled'))

        channel = c.get('notify_channel', 'disabled')
        if channel == 'dingtalk':
            self.webhook_input.setText(c.get('dingtalk_webhook', ''))
        elif channel == 'bark':
            self.webhook_input.setText(c.get('bark_key', ''))

        self.default_copies_spin.setValue(c.get('default_copies', 1))
        self.default_duplex_cb.setChecked(c.get('default_duplex', False))
        self.default_color_cb.setChecked(c.get('default_color', True))
        self.paper_size_combo.setCurrentText(c.get('paper_size', 'A4'))
        self.worker_count_spin.setValue(c.get('worker_count', 2))
        self.max_file_size_spin.setValue(c.get('max_file_size_mb', 50))
        self.print_dpi_spin.setValue(c.get('print_dpi', 600))
        self.word_timeout_spin.setValue(c.get('word_timeout', 120))
        self.log_level_combo.setCurrentText(c.get('log_level', 'INFO'))
        self.log_max_days_spin.setValue(c.get('job_retention_days', 30))

    def _populate_printers(self):
        monitor = getattr(self._mw._app.state, 'printer_monitor', None)
        if monitor is None:
            return
        self.default_printer_combo.clear()
        self.default_printer_combo.addItem('')
        raw = monitor.get_all_statuses()
        for name in raw:
            self.default_printer_combo.addItem(name)
        default = self._config.get('default_printer', '') if self._config else ''
        idx = self.default_printer_combo.findText(default)
        if idx >= 0:
            self.default_printer_combo.setCurrentIndex(idx)

    _RESTART_KEYS = {
        'port',
        'ssl_enabled',
        'worker_count',
        'log_level',
        'job_timeout',
        'word_timeout',
        'print_dpi',
        'max_file_size_mb',
    }

    def _show_restart_dialog(self):
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        dlg = QDialog(self)
        dlg.setWindowTitle('需要重启')
        dlg.setMinimumWidth(380)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(16)
        msg = QLabel('部分设置需要重启服务器才能生效。')
        msg.setWordWrap(True)
        layout.addWidget(msg)
        btn_row = QHBoxLayout()
        later_btn = QPushButton('稍后')
        later_btn.setObjectName('ghost')
        later_btn.clicked.connect(dlg.reject)
        restart_btn = QPushButton('立即重启')
        restart_btn.setObjectName('primary')
        restart_btn.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(later_btn)
        btn_row.addWidget(restart_btn)
        layout.addLayout(btn_row)
        return dlg.exec() == QDialog.DialogCode.Accepted

    def _save(self):
        if not self._config:
            self.status_label.setText('配置不可用')
            self.status_label.setStyleSheet('color: #C53A3A;')
            return
        self.save_btn.set_loading()
        try:
            channel = self.notify_channel_combo.currentText()
            webhook_val = self.webhook_input.text()
            updates = {
                'api_key': self.api_key_input.text(),
                'port': int(self.port_input.text()),
                'quark_api_key_id': self.quark_key_id_input.text(),
                'quark_api_key': self.quark_key_input.text(),
                'ssl_enabled': self.ssl_cb.isChecked(),
                'default_printer': self.default_printer_combo.currentText(),
                'job_timeout': self.timeout_spin.value(),
                'auto_retry_count': self.retry_spin.value(),
                'notify_channel': channel,
                'default_copies': self.default_copies_spin.value(),
                'default_duplex': self.default_duplex_cb.isChecked(),
                'default_color': self.default_color_cb.isChecked(),
                'paper_size': self.paper_size_combo.currentText(),
                'worker_count': self.worker_count_spin.value(),
                'max_file_size_mb': self.max_file_size_spin.value(),
                'print_dpi': self.print_dpi_spin.value(),
                'word_timeout': self.word_timeout_spin.value(),
                'log_level': self.log_level_combo.currentText(),
                'job_retention_days': self.log_max_days_spin.value(),
            }
            if channel == 'dingtalk':
                updates['dingtalk_webhook'] = webhook_val
            elif channel == 'bark':
                updates['bark_key'] = webhook_val

            # Detect restart-required keys
            old = {k: self._config.get(k) for k in self._RESTART_KEYS}
            self._config.set_many(updates)
            self._config.save()
            self.save_btn.set_success()
            if hasattr(self._mw, 'show_notification'):
                self._mw.show_notification('设置已保存', '#6B8F6B')
            self.status_label.setText('')

            # Check if restart is needed
            needs_restart = any(
                str(self._config.get(k)) != str(old.get(k)) for k in self._RESTART_KEYS
            )
            if needs_restart:
                self.restart_label.setVisible(True)
                if self._show_restart_dialog():
                    self._mw._on_restart()
        except Exception as e:
            self.save_btn.set_error()
            self.status_label.setText(f'保存失败: {e}')
            self.status_label.setStyleSheet('color: #C53A3A;')

    def _test_notification(self):
        from app.core.config import Config
        from app.services.notifications.bark import BarkNotifier
        from app.services.notifications.dingtalk import DingTalk

        cfg = Config()
        channel = cfg.get('notify_channel', 'disabled')
        if channel == 'bark':
            notifier = BarkNotifier(cfg)
        elif channel == 'dingtalk':
            notifier = DingTalk(cfg)
        else:
            self.test_notify_btn.set_error('未配置通知渠道')
            return
        self.test_notify_btn.set_loading()
        try:
            notifier.notify_job_completed('测试文件.pdf', '2024-01-01 12:00:00')
            self.test_notify_btn.set_success()
            if hasattr(self._mw, 'show_notification'):
                self._mw.show_notification('测试通知发送成功', '#6B8F6B')
        except Exception as e:
            self.test_notify_btn.set_error(str(e))
