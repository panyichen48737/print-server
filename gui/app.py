"""MainWindow: nav sidebar + QStackedWidget + status bar + system tray."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QTimer
from PySide6.QtGui import QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget, QMenu,
)

from console._server import ServerHandle
from gui.event_bridge import EventBridge


class MainWindow(QMainWindow):
    NAV_ITEMS = ["仪表盘", "快速打印", "任务管理", "实时日志", "设置", "打印机管理", "关于"]

    def __init__(self, app, config, server_handle: ServerHandle):
        super().__init__()
        self._app = app
        self._config = config
        self._server = server_handle
        self._event_bus = app.state.event_bus

        # EventBridge — thread-safe EventBus to Qt signal bridge
        self._bridge = EventBridge(self._event_bus, self)
        self._bridge.job_status.connect(self._on_job_status)
        self._bridge.printer_status.connect(self._on_printer_status)
        self._bridge.log.connect(self._on_log)

        self.setWindowTitle("iOS 云打印服务器")
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Status bar (top)
        self.status_bar = self._build_status_bar()

        # Nav sidebar
        self.nav = QListWidget()
        self.nav.setFixedWidth(160)
        for label in self.NAV_ITEMS:
            QListWidgetItem(label, self.nav)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        # Page container
        self.stack = QStackedWidget()
        from gui.pages.dashboard import DashboardPage
        from gui.pages.quick_print import QuickPrintPage
        from gui.pages.job_manager import JobManagerPage
        from gui.pages.logs import LogsPage
        from gui.pages.settings import SettingsPage
        from gui.pages.printer_manager import PrinterManagerPage
        from gui.pages.about import AboutPage

        self.stack.addWidget(DashboardPage(self))
        self.stack.addWidget(QuickPrintPage(self))
        self.stack.addWidget(JobManagerPage(self))
        self.stack.addWidget(LogsPage(self))
        self.stack.addWidget(SettingsPage(self))
        self.stack.addWidget(PrinterManagerPage(self))
        self.stack.addWidget(AboutPage(self))

        # Layout: status bar top, then nav + content below
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        content_row.addWidget(self.nav)
        content_row.addWidget(self.stack, 1)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self.status_bar)
        container_layout.addLayout(content_row, 1)
        main_layout.addWidget(container)

        # System tray
        self._setup_tray()

        # Health timer
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._refresh_status)
        self._health_timer.start(3000)

        # Window state persistence
        from gui.settings_store import WindowStateManager
        self._state_manager = WindowStateManager(self)
        self._state_manager.restore()

        # Select first page
        self.nav.setCurrentRow(0)
        self._setup_shortcuts()

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        self.status_dot = QLabel("●")
        self.status_text = QLabel("启动中...")
        self.start_btn = QPushButton("启动")
        self.stop_btn = QPushButton("停止")
        self.restart_btn = QPushButton("重启")
        self.web_btn = QPushButton("管理后台")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.restart_btn.clicked.connect(self._on_restart)
        self.web_btn.clicked.connect(self._on_open_web)
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_text)
        layout.addStretch()
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.restart_btn)
        layout.addWidget(self.web_btn)
        return bar

    def _setup_tray(self):
        icon_path = str(Path(__file__).parent / "resources" / "icon.png")
        if Path(icon_path).exists():
            self.tray = QSystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("iOS 云打印服务器")
        menu = QMenu()
        show_action = menu.addAction("显示窗口")
        show_action.triggered.connect(self.show)
        menu.addSeparator()
        start_action = menu.addAction("启动服务器")
        start_action.triggered.connect(self._on_start)
        stop_action = menu.addAction("停止服务器")
        stop_action.triggered.connect(self._on_stop)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._on_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()

    def _on_quit(self):
        if self._server:
            self._server.stop()
        QApplication.quit()

    def _on_start(self):
        if self._server:
            self._server.start(self._app, self._config)

    def _on_stop(self):
        if self._server:
            self._server.stop()

    def _on_restart(self):
        if self._server:
            self._server.stop()
            self._server.start(self._app, self._config)

    def _on_open_web(self):
        import webbrowser
        port = self._server.port if self._server else 5000
        webbrowser.open(f"http://127.0.0.1:{port}/admin")

    def _refresh_status(self):
        if self._server and self._server.is_running:
            self.status_dot.setStyleSheet("color: green;")
            self.status_text.setText(f"运行中 · 端口 {self._server.port}")
            self.start_btn.setVisible(False)
            self.stop_btn.setVisible(True)
        elif self._server:
            self.status_dot.setStyleSheet("color: red;")
            self.status_text.setText("已停止")
            self.start_btn.setVisible(True)
            self.stop_btn.setVisible(False)
        else:
            self.status_dot.setStyleSheet("color: gray;")
            self.status_text.setText("未初始化")

    def _setup_shortcuts(self):
        for i in range(7):
            sc = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            sc.activated.connect(lambda idx=i: self.nav.setCurrentRow(idx))

        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(lambda: self.nav.setCurrentRow(1))
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("F5"), self).activated.connect(self._refresh_current)

    def _focus_search(self):
        w = self.stack.currentWidget()
        for attr in ["search_input", "search", "filter_input"]:
            field = getattr(w, attr, None)
            if field and hasattr(field, "setFocus"):
                field.setFocus()
                return

    def _refresh_current(self):
        w = self.stack.currentWidget()
        if hasattr(w, "_refresh"):
            w._refresh()

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)
        w = self.stack.currentWidget()
        if w:
            anim = QPropertyAnimation(w, b"windowOpacity")
            anim.setDuration(200)
            anim.setStartValue(0.7)
            anim.setEndValue(1.0)
            anim.start()

    def _on_log(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, "on_log"):
            current.on_log(data)

    def _on_job_status(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, "on_job_status"):
            current.on_job_status(data)
        status = data.get("status", "")
        if status == "completed":
            self.tray.showMessage("打印完成", f"任务 #{data['job_id']} 已完成", QSystemTrayIcon.MessageIcon.Information, 3000)
        elif status == "failed":
            self.tray.showMessage("打印失败", f"任务 #{data['job_id']} 失败: {data.get('error', '')}", QSystemTrayIcon.MessageIcon.Critical, 5000)

    def _on_printer_status(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, "on_printer_status"):
            current.on_printer_status(data)

    def closeEvent(self, event):
        self._state_manager.save()
        event.ignore()
        self.hide()


def run_gui(app, config, server_handle: ServerHandle):
    qapp = QApplication(sys.argv)
    from gui.theme import ThemeEngine
    theme = ThemeEngine.instance()
    theme.apply("light", qapp)
    window = MainWindow(app, config, server_handle)
    window.show()
    qapp.aboutToQuit.connect(window._bridge.stop)
    sys.exit(qapp.exec())