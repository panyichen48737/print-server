"""First-launch setup wizard: guides user through essential configuration."""

from __future__ import annotations

import secrets
import socket
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.components.toggle_switch import LabeledToggle
from gui.components.validators import PortValidator


class SetupWizard(QDialog):
    """Multi-step setup wizard for first launch."""

    STEPS = ['欢迎', 'API Key', '服务器', 'Quark API', '打印机', '完成']

    def __init__(self, config, printer_monitor=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._printer_monitor = printer_monitor
        self._current_step = 0
        self._page_widgets: list[QWidget] = []
        self._step_labels: list[QPushButton] = []

        self.setWindowTitle('首次配置向导')
        self.setMinimumSize(720, 520)
        self.setModal(True)
        self.setObjectName('setupWizard')
        self._set_window_icon()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # ── Left: Step indicator ──
        step_panel = QFrame()
        step_panel.setFixedWidth(160)
        step_panel.setObjectName('sidebar')
        step_layout = QVBoxLayout(step_panel)
        step_layout.setContentsMargins(16, 24, 16, 24)
        step_layout.setSpacing(4)

        for i, name in enumerate(self.STEPS):
            btn = QPushButton(f'{i + 1}. {name}')
            btn.setObjectName('navItem')
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self._go_to(idx))
            self._step_labels.append(btn)
            step_layout.addWidget(btn)

        step_layout.addStretch()
        body.addWidget(step_panel)

        # ── Right: Content pages ──
        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)
        main_layout.addLayout(body, 1)

        # ── Bottom: Navigation bar ──
        nav_bar = QFrame()
        nav_bar.setObjectName('wizardNav')
        nav = QHBoxLayout(nav_bar)
        nav.setContentsMargins(20, 12, 20, 16)
        nav.setSpacing(8)

        self.prev_btn = QPushButton('上一步')
        self.prev_btn.setObjectName('ghost')
        self.prev_btn.clicked.connect(self._go_prev)

        self.next_btn = QPushButton('下一步')
        self.next_btn.setObjectName('primary')
        self.next_btn.clicked.connect(self._go_next)

        self.finish_btn = QPushButton('完成配置')
        self.finish_btn.setObjectName('primary')
        self.finish_btn.clicked.connect(self._finish)
        self.finish_btn.setVisible(False)

        self.skip_btn = QPushButton('跳过')
        self.skip_btn.setObjectName('ghostDanger')
        self.skip_btn.clicked.connect(self._skip)

        nav.addWidget(self.prev_btn)
        nav.addStretch()
        nav.addWidget(self.skip_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.finish_btn)
        main_layout.addWidget(nav_bar)

        # Build pages
        self._build_welcome()
        self._build_api_key()
        self._build_server()
        self._build_quark()
        self._build_printer()
        self._build_complete()

        self._update_nav()

    def _set_window_icon(self):
        if getattr(sys, 'frozen', False):
            icon_path = Path(sys.executable).parent / 'gui' / 'resources' / 'icon_256.png'
        else:
            icon_path = Path(__file__).parent.parent / 'resources' / 'icon_256.png'
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    # ── Page builders ──

    def _page(self, spacing=16):
        """Create a standard page with top margin."""
        w = QWidget()
        lo = QVBoxLayout(w)
        lo.setContentsMargins(28, 32, 28, 16)
        lo.setSpacing(spacing)
        lo.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._page_widgets.append(w)
        self.stack.addWidget(w)
        return lo

    def _heading(self, parent, text: str):
        h = QLabel(text)
        h.setObjectName('pageTitle')
        parent.addWidget(h)

    def _desc(self, parent, text: str, wrap=True):
        d = QLabel(text)
        d.setObjectName('pageSub')
        d.setWordWrap(wrap)
        parent.addWidget(d)

    def _build_welcome(self):
        lo = self._page()
        self._heading(lo, '欢迎使用 iOS 云打印服务器')
        self._desc(lo, '本向导将帮助你完成服务器的基础配置，只需几步即可开始使用。')
        lo.addSpacing(20)

        features = QLabel(
            '• 支持 PDF / Office / 图片打印\n'
            '• 从 iOS Scriptable 或 Web 端提交任务\n'
            '• 实时任务监控和管理\n'
            '• 文档扫描（需夸克 API）'
        )
        lo.addWidget(features)

    def _build_api_key(self):
        lo = self._page()
        self._heading(lo, 'API Key')
        self._desc(
            lo,
            'API Key 用于客户端认证，请设置一个安全的密钥。iOS Scriptable 端需要配置相同的 Key 才能连接。',
        )

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText('输入或生成 API Key')
        self.api_key_input.setText(self._config.get('api_key', ''))
        lo.addWidget(self.api_key_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        gen_btn = QPushButton('随机生成')
        gen_btn.setObjectName('ghost')
        gen_btn.clicked.connect(self._generate_key)
        copy_btn = QPushButton('复制')
        copy_btn.setObjectName('ghost')
        copy_btn.clicked.connect(self._copy_key)
        btn_row.addWidget(gen_btn)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        lo.addLayout(btn_row)

    def _build_server(self):
        lo = self._page()
        self._heading(lo, '服务器设置')
        self._desc(lo, '配置服务器监听端口和 SSL。端口默认 5000，一般不需要修改。')

        port_row = QHBoxLayout()
        port_row.setSpacing(8)
        port_row.addWidget(QLabel('端口:'))
        self.port_input = QLineEdit(str(self._config.get('port', 5000)))
        self.port_input.setValidator(PortValidator(self))
        self.port_input.setFixedWidth(120)
        port_row.addWidget(self.port_input)
        port_row.addStretch()
        lo.addLayout(port_row)

        self.ssl_toggle = LabeledToggle(
            '启用 SSL', checked=self._config.get('ssl_enabled', True), label_first=True
        )
        lo.addWidget(self.ssl_toggle)

    def _build_quark(self):
        lo = self._page()
        self._heading(lo, '夸克扫描 API（可选）')
        self._desc(
            lo, '配置夸克扫描 API 后可使用文档扫描和图片文字识别功能。如不需要可跳过此步骤。'
        )

        lo.addSpacing(8)
        form_row1 = QHBoxLayout()
        form_row1.setSpacing(8)
        form_row1.addWidget(QLabel('Key ID:'))
        self.quark_key_id = QLineEdit(self._config.get('quark_api_key_id', ''))
        form_row1.addWidget(self.quark_key_id, 1)
        lo.addLayout(form_row1)

        form_row2 = QHBoxLayout()
        form_row2.setSpacing(8)
        form_row2.addWidget(QLabel('API Key:'))
        self.quark_key = QLineEdit(self._config.get('quark_api_key', ''))
        self.quark_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_row2.addWidget(self.quark_key, 1)
        lo.addLayout(form_row2)

        note = QLabel('提示：可在设置页面随时修改这些配置。')
        lo.addWidget(note)

    def _build_printer(self):
        lo = self._page()
        self._heading(lo, '打印机设置')
        self._desc(lo, '选择默认打印机并设置基本打印选项。')

        lo.addSpacing(8)
        pr_row = QHBoxLayout()
        pr_row.setSpacing(8)
        pr_row.addWidget(QLabel('默认打印机:'))
        self.printer_combo = QComboBox()
        self.printer_combo.setMinimumWidth(200)
        pr_row.addWidget(self.printer_combo, 1)
        pr_row.addStretch()
        lo.addLayout(pr_row)

        # Populate printers from monitor
        if self._printer_monitor:
            raw = self._printer_monitor.get_all_statuses()
            for name in raw:
                self.printer_combo.addItem(name)
        default_printer = self._config.get('default_printer', '')
        if default_printer:
            idx = self.printer_combo.findText(default_printer)
            if idx >= 0:
                self.printer_combo.setCurrentIndex(idx)

        copies_row = QHBoxLayout()
        copies_row.setSpacing(8)
        copies_row.addWidget(QLabel('默认份数:'))
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(self._config.get('default_copies', 1))
        copies_row.addWidget(self.copies_spin)
        copies_row.addStretch()
        lo.addLayout(copies_row)

        self.duplex_toggle = LabeledToggle(
            '双面', checked=self._config.get('default_duplex', False), label_first=True
        )
        lo.addWidget(self.duplex_toggle)
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        color_row.addWidget(QLabel('默认颜色:'))
        self.color_combo = QComboBox()
        self.color_combo.addItems(['彩色', '黑白'])
        self.color_combo.setCurrentText(
            '彩色' if self._config.get('default_color', True) else '黑白'
        )
        color_row.addWidget(self.color_combo)
        color_row.addStretch()
        lo.addLayout(color_row)

        paper_row = QHBoxLayout()
        paper_row.setSpacing(8)
        paper_row.addWidget(QLabel('纸张大小:'))
        self.paper_combo = QComboBox()
        self.paper_combo.addItems(['A4', 'Letter', 'A3'])
        self.paper_combo.setCurrentText(self._config.get('paper_size', 'A4'))
        paper_row.addWidget(self.paper_combo)
        paper_row.addStretch()
        lo.addLayout(paper_row)

    def _build_complete(self):
        lo = self._page(spacing=12)
        self._heading(lo, '配置完成！')
        self._desc(lo, '以下是你的服务器连接信息，请在 iOS Scriptable 中使用。')

        lo.addSpacing(12)

        # Local IP
        ip = self._get_local_ip()
        summary = QWidget()
        summary.setObjectName('statCard')
        slo = QVBoxLayout(summary)
        slo.setContentsMargins(20, 16, 20, 16)
        slo.setSpacing(8)

        def _info_row(label, value, copyable=True):
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label)
            lbl.setObjectName('muted')
            val = QLabel(value)
            val.setObjectName('data')
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(lbl)
            row.addWidget(val, 1)
            if copyable:
                cp = QPushButton('复制')
                cp.setObjectName('ghost')
                cp.setProperty('compact', True)
                cp.clicked.connect(lambda _, v=value: self._copy_text(v))
                row.addWidget(cp)
            slo.addLayout(row)

        port = self.port_input.text() if hasattr(self, 'port_input') else '5000'
        _info_row('服务器地址', f'http://{ip}:{port}')
        _info_row('API Key', self.api_key_input.text() if hasattr(self, 'api_key_input') else '')
        lo.addWidget(summary)

        lo.addSpacing(16)

        # Quick start guide
        guide = QLabel(
            '快速开始：\n'
            f'1. 打开 iOS Scriptable\n'
            f'2. 在脚本中设置 serverUrl = "http://{ip}:{port}"\n'
            f'3. 设置 apiKey = "{self.api_key_input.text()[:16]}…"\n'
            '4. 即可从 iOS 提交打印任务'
        )
        guide.setObjectName('statCard')
        lo.addWidget(guide)

    # ── Helpers ──

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'

    def _generate_key(self):
        key = secrets.token_hex(32)
        self.api_key_input.setText(key)

    def _copy_key(self):
        self._copy_text(self.api_key_input.text())

    def _copy_text(self, text: str):
        cb = self.clipboard() if hasattr(self, 'clipboard') else None
        if cb:
            cb.setText(text)

    def clipboard(self):
        from PySide6.QtGui import QGuiApplication

        return QGuiApplication.clipboard()

    # ── Navigation ──

    def _go_to(self, index: int):
        if 0 <= index < len(self.STEPS):
            self._current_step = index
            self.stack.setCurrentIndex(index)
            self._update_nav()

    def _go_next(self):
        if self._current_step < len(self.STEPS) - 1:
            self._go_to(self._current_step + 1)

    def _go_prev(self):
        if self._current_step > 0:
            self._go_to(self._current_step - 1)

    def _skip(self):
        self.reject()

    def _finish(self):
        # Save all config
        self._save_config()
        self.accept()

    def _save_config(self):
        c = self._config
        c.set('api_key', self.api_key_input.text())
        c.set('port', int(self.port_input.text()))
        c.set('ssl_enabled', self.ssl_toggle.isChecked())
        c.set('quark_api_key_id', self.quark_key_id.text())
        c.set('quark_api_key', self.quark_key.text())
        c.set('default_printer', self.printer_combo.currentText())
        c.set('default_copies', self.copies_spin.value())
        c.set('default_duplex', self.duplex_toggle.isChecked())
        c.set('default_color', self.color_combo.currentText() == '彩色')
        c.set('paper_size', self.paper_combo.currentText())
        c.save()

    def _update_nav(self):
        total = len(self.STEPS)
        is_first = self._current_step == 0
        is_last = self._current_step == total - 1

        self.prev_btn.setVisible(not is_first)
        self.next_btn.setVisible(not is_last)
        self.finish_btn.setVisible(is_last)
        self.skip_btn.setVisible(not is_last)

        for i, btn in enumerate(self._step_labels):
            active = i == self._current_step
            btn.setProperty('active', active)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
