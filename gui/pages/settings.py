"""Settings page with 7 config groups."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from gui.components.stateful_button import StatefulButton
from gui.components.validators import PortValidator


class SettingsPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._config = getattr(main_window, "_config", None)
        self._changed_keys: set[str] = set()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        layout.addWidget(QLabel("设置", styleSheet="font-size: 24px; font-weight: bold;"))

        # Group 1: Security
        security_group = QGroupBox("安全")
        security_form = QFormLayout(security_group)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        security_form.addRow("API Key:", self.api_key_input)
        self.auth_enabled_cb = QCheckBox("启用 API 认证")
        security_form.addRow("", self.auth_enabled_cb)
        layout.addWidget(security_group)

        # Group 2: Server
        server_group = QGroupBox("服务器")
        server_form = QFormLayout(server_group)
        self.port_input = QLineEdit()
        self.port_input.setValidator(PortValidator(self))
        server_form.addRow("端口:", self.port_input)
        self.host_input = QLineEdit()
        server_form.addRow("监听地址:", self.host_input)
        self.ssl_cb = QCheckBox("启用 SSL")
        server_form.addRow("", self.ssl_cb)
        layout.addWidget(server_group)

        # Group 3: Printer
        printer_group = QGroupBox("打印机")
        printer_form = QFormLayout(printer_group)
        self.default_printer_combo = QComboBox()
        printer_form.addRow("默认打印机:", self.default_printer_combo)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 300)
        self.timeout_spin.setSuffix(" 秒")
        printer_form.addRow("打印超时:", self.timeout_spin)
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        printer_form.addRow("重试次数:", self.retry_spin)
        layout.addWidget(printer_group)

        # Group 4: Notification
        notif_group = QGroupBox("通知")
        notif_form = QFormLayout(notif_group)
        self.notify_channel_combo = QComboBox()
        self.notify_channel_combo.addItems(["disabled", "dingtalk", "bark"])
        notif_form.addRow("通知渠道:", self.notify_channel_combo)
        self.webhook_input = QLineEdit()
        notif_form.addRow("Webhook URL:", self.webhook_input)
        self.test_notify_btn = StatefulButton("测试通知")
        notif_form.addRow("", self.test_notify_btn)
        layout.addWidget(notif_group)

        # Group 5: Print Options
        print_opts_group = QGroupBox("打印选项")
        print_opts_form = QFormLayout(print_opts_group)
        self.default_copies_spin = QSpinBox()
        self.default_copies_spin.setRange(1, 99)
        print_opts_form.addRow("默认份数:", self.default_copies_spin)
        self.default_duplex_cb = QCheckBox("双面")
        self.default_duplex_cb.setChecked(True)
        print_opts_form.addRow("", self.default_duplex_cb)
        self.default_color_cb = QCheckBox("颜色")
        print_opts_form.addRow("", self.default_color_cb)
        self.paper_size_combo = QComboBox()
        self.paper_size_combo.addItems(["A4", "Letter", "A3"])
        print_opts_form.addRow("默认纸张:", self.paper_size_combo)
        layout.addWidget(print_opts_group)

        # Group 6: Logging
        log_group = QGroupBox("日志")
        log_form = QFormLayout(log_group)
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        log_form.addRow("日志级别:", self.log_level_combo)
        self.log_max_days_spin = QSpinBox()
        self.log_max_days_spin.setRange(1, 90)
        log_form.addRow("日志保留天数:", self.log_max_days_spin)
        layout.addWidget(log_group)

        # Group 7: About - build info
        about_group = QGroupBox("版本信息")
        about_form = QFormLayout(about_group)
        version_label = QLabel("1.6.0")
        about_form.addRow("版本:", version_label)
        build_label = QLabel("2026-05-08")
        about_form.addRow("构建日期:", build_label)
        layout.addWidget(about_group)

        # Save button
        self.save_btn = StatefulButton("保存设置")
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self.save_btn)

        # Status label
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        layout.addStretch()
        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

    def _save(self):
        if not self._config:
            self.status_label.setText("配置不可用")
            self.status_label.setStyleSheet("color: #DC2626;")
            return
        self.save_btn.set_loading()
        try:
            updates = {
                "api_key": self.api_key_input.text(),
                "auth_enabled": self.auth_enabled_cb.isChecked(),
                "port": int(self.port_input.text()),
                "host": self.host_input.text(),
                "ssl_enabled": self.ssl_cb.isChecked(),
                "timeout": self.timeout_spin.value(),
                "retry_count": self.retry_spin.value(),
                "notify_channel": self.notify_channel_combo.currentText(),
                "webhook_url": self.webhook_input.text(),
                "default_copies": self.default_copies_spin.value(),
                "default_duplex": self.default_duplex_cb.isChecked(),
                "default_color": self.default_color_cb.isChecked(),
                "paper_size": self.paper_size_combo.currentText(),
                "log_level": self.log_level_combo.currentText(),
                "log_max_days": self.log_max_days_spin.value(),
            }
            self._config.set_many(updates)
            self._config.save()
            self.save_btn.set_success()
            self.status_label.setText("设置已保存")
            self.status_label.setStyleSheet("color: #16A34A;")
        except Exception as e:
            self.save_btn.set_error()
            self.status_label.setText(f"保存失败: {e}")
            self.status_label.setStyleSheet("color: #DC2626;")