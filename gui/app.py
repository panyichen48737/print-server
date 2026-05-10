"""MainWindow: SidebarWidget + QStackedWidget + bottom status bar + system tray."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from gui.components.sidebar import SidebarWidget
from gui.event_bridge import EventBridge
from launcher._server import ServerHandle


class MainWindow(QMainWindow):
    NAV_ITEMS = ['仪表盘', '快速打印', '文档扫描', '任务管理', '实时日志', '设置', '关于']

    def __init__(self, app, config, server_handle: ServerHandle):
        super().__init__()
        self._app = app
        self._config = config
        self._server = server_handle
        self._theme_mode = 'light'
        self._event_bus = app.state.event_bus
        self._pending_update = None
        self._service_pending_update = None
        self._last_queue_size = 0
        self._idle_timer = None

        # EventBridge — thread-safe EventBus to Qt signal bridge
        self._bridge = EventBridge(self._event_bus, self)
        self._bridge.job_status.connect(self._on_job_status)
        self._bridge.printer_status.connect(self._on_printer_status)
        self._bridge.health_status.connect(self._on_health_status)
        self._bridge.log.connect(self._on_log)

        # Notification stack (bottom-right toasts)
        from gui.components.notification import NotificationStack

        self._notifications = NotificationStack(self)

        self.setWindowTitle('iOS 云打印服务器')
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Body: sidebar + content
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Sidebar
        self.sidebar = SidebarWidget()
        self.sidebar.currentRowChanged.connect(self._on_nav_changed)
        body.addWidget(self.sidebar)

        # Page container
        self.stack = QStackedWidget()
        from gui.pages.about import AboutPage
        from gui.pages.dashboard import DashboardPage
        from gui.pages.job_manager import JobManagerPage
        from gui.pages.logs import LogsPage
        from gui.pages.quick_print import QuickPrintPage
        from gui.pages.scan import ScanPage
        from gui.pages.settings import SettingsPage

        self.stack.addWidget(DashboardPage(self))
        self.stack.addWidget(QuickPrintPage(self))
        self.stack.addWidget(ScanPage(self))
        self.stack.addWidget(JobManagerPage(self))
        self.stack.addWidget(LogsPage(self))
        self.stack.addWidget(SettingsPage(self))
        self.stack.addWidget(AboutPage(self))

        body.addWidget(self.stack, 1)
        main_layout.addLayout(body, 1)

        # Status bar (bottom)
        self.status_bar = self._build_status_bar()
        main_layout.addWidget(self.status_bar)

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
        self.sidebar.setCurrentRow(0)

        # Position notification stack bottom-right
        self._notifications.raise_()

        # Auto-update check (deferred to avoid delaying startup)
        auto_enabled = self._config.get('auto_update_check', True) if self._config else True
        if auto_enabled:
            QTimer.singleShot(8000, self._check_auto_update)

        # Check if service already has a pre-downloaded update
        QTimer.singleShot(10000, self._check_service_pending)

    def show_notification(self, text: str, color: str = '#8B7355'):
        self._notifications.show_notification(text, color)

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName('statusBar')
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet('background-color: #6B8F6B; border-radius: 4px;')
        self.status_text = QLabel('启动中...')
        self.status_text.setObjectName('statusText')
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_text)

        layout.addStretch()

        self.start_btn = QPushButton('启动')
        self.start_btn.setObjectName('statusPillSuccess')
        self.stop_btn = QPushButton('停止')
        self.stop_btn.setObjectName('statusPill')
        self.restart_btn = QPushButton('重启')
        self.restart_btn.setObjectName('statusPill')
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.restart_btn.clicked.connect(self._on_restart)

        pills = QWidget()
        pill_lo = QHBoxLayout(pills)
        pill_lo.setContentsMargins(0, 0, 0, 0)
        pill_lo.setSpacing(6)
        pill_lo.addWidget(self.start_btn)
        pill_lo.addWidget(self.stop_btn)
        pill_lo.addWidget(self.restart_btn)
        layout.addWidget(pills)
        return bar

    def _setup_tray(self):
        if getattr(sys, 'frozen', False):
            icon_path = str(Path(sys.executable).parent / 'gui' / 'resources' / 'icon_256.png')
        else:
            icon_path = str(Path(__file__).parent / 'resources' / 'icon_256.png')
        self._app_icon = QIcon(icon_path) if Path(icon_path).exists() else QIcon()
        self.setWindowIcon(self._app_icon)
        if Path(icon_path).exists():
            self.tray = QSystemTrayIcon(self._app_icon, self)
        else:
            self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip('iOS 云打印服务器')
        menu = QMenu()
        show_action = menu.addAction('显示窗口')
        show_action.triggered.connect(self.show)
        menu.addSeparator()
        start_action = menu.addAction('启动服务器')
        start_action.triggered.connect(self._on_start)
        stop_action = menu.addAction('停止服务器')
        stop_action.triggered.connect(self._on_stop)
        menu.addSeparator()
        self.theme_action = menu.addAction('深色主题')
        self.theme_action.triggered.connect(self._toggle_theme)
        menu.addSeparator()
        update_action = menu.addAction('检查更新')
        update_action.triggered.connect(self._tray_check_update)
        menu.addSeparator()
        quit_action = menu.addAction('退出')
        quit_action.triggered.connect(self._on_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.messageClicked.connect(self._on_tray_message_clicked)
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

    # ── Auto-update ──

    def _check_auto_update(self):
        """Background check for updates on startup."""
        import threading

        from app.updater import check_latest_version

        def _worker():
            info = check_latest_version()
            if info and info.is_newer and info.download_url:
                QTimer.singleShot(0, self._on_auto_update_found)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_auto_update_found(self):
        self._pending_update = True
        self.tray.showMessage(
            '更新可用',
            '新版本已发布，点击查看',
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )
        self.show_notification('新版本可用 - 前往「关于」页面更新', '#B8956A')

    def _check_service_pending(self):
        """Check if update service has a pre-downloaded update ready."""
        from gui.pipe_client import pending_update

        info = pending_update()
        if info is None:
            return

        self._pending_update = True
        self._service_pending_update = info
        self.show_notification(f'更新 {info.version} 已下载，空闲后将自动重启', '#6B8F6B')

        # Start idle monitor to auto-apply when no active tasks
        if not hasattr(self, '_idle_timer') or not self._idle_timer:
            self._idle_timer = QTimer(self)
            self._idle_timer.timeout.connect(self._check_idle_and_apply)
            self._idle_timer.start(5000)

    def _check_idle_and_apply(self):
        """Auto-apply update when server is idle (no active jobs)."""
        if not self._server or not self._server.is_running:
            return
        if not getattr(self, '_service_pending_update', None):
            return
        # Check queue_size from health status — 0 means idle
        if getattr(self, '_last_queue_size', None) != 0:
            return
        # Also avoid applying while user is actively using the GUI
        if self.isVisible() and self.isActiveWindow():
            return

        self._auto_apply_service_update()

    def _auto_apply_service_update(self):
        """Tell service to apply update, then exit."""
        import os

        from gui.pipe_client import apply_update

        info = getattr(self, '_service_pending_update', None)
        if not info:
            return

        if self._server:
            self._server.stop()

        app_dir = str(Path(sys.executable).parent) if getattr(sys, 'frozen', False) else None
        apply_update(info.zip_path, app_dir)
        self.show_notification('正在更新，程序即将重启...', '#6B8F6B')
        QTimer.singleShot(2000, lambda: os._exit(0))

    def _tray_check_update(self):
        about_idx = self.NAV_ITEMS.index('关于')
        self.sidebar.setCurrentRow(about_idx)
        about_page = self.stack.widget(about_idx)
        if hasattr(about_page, '_check_update'):
            about_page._check_update()
        self.show()
        self.raise_()

    def _on_tray_message_clicked(self):
        about_idx = self.NAV_ITEMS.index('关于')
        self.sidebar.setCurrentRow(about_idx)
        about_page = self.stack.widget(about_idx)
        if hasattr(about_page, '_check_update') and getattr(self, '_pending_update', None):
            about_page._check_update()
            self._pending_update = None
        self.show()
        self.raise_()

    def _toggle_theme(self):
        from gui.theme import ThemeEngine

        theme = ThemeEngine.instance()
        new_mode = 'dark' if self._theme_mode == 'light' else 'light'
        theme.apply(new_mode, QApplication.instance())
        self._theme_mode = new_mode
        self.theme_action.setText('浅色主题' if new_mode == 'dark' else '深色主题')
        # Persist to config
        if self._config:
            self._config.set('theme_mode', new_mode)
            self._config.save()

    def _refresh_status(self):
        if self._server and self._server.is_running:
            self.status_dot.setStyleSheet('background-color: #6B8F6B; border-radius: 4px;')
            self.status_text.setText(f'运行中 · 端口 {self._server.port}')
            self.start_btn.setVisible(True)
            self.stop_btn.setVisible(True)
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.sidebar.set_server_status(True, self._server.port)
        elif self._server:
            self.status_dot.setStyleSheet('background-color: #C53A3A; border-radius: 4px;')
            self.status_text.setText('已停止')
            self.start_btn.setVisible(True)
            self.stop_btn.setVisible(True)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.sidebar.set_server_status(False)
        else:
            self.status_dot.setStyleSheet('background-color: #B0A89F; border-radius: 4px;')
            self.status_text.setText('未初始化')

    def _on_nav_changed(self, index: int):
        current = self.stack.currentWidget()
        if current and getattr(current, '_has_unsaved_content', lambda: False)():
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                '未保存更改',
                '当前页面有未提交的文件，离开后数据将清空，是否离开？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                # Block navigation — revert sidebar selection
                self.sidebar.blockSignals(True)
                self.sidebar.setCurrentRow(self.stack.currentIndex())
                self.sidebar.blockSignals(False)
                return
            # Clear current page
            if hasattr(current, '_clear_all'):
                current._clear_all()

        self.stack.setCurrentIndex(index)
        w = self.stack.currentWidget()
        if w:
            anim = QPropertyAnimation(w, b'windowOpacity')
            anim.setDuration(200)
            anim.setStartValue(0.7)
            anim.setEndValue(1.0)
            anim.start()

    def _on_log(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, 'on_log'):
            current.on_log(data)

    def _on_job_status(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, 'on_job_status'):
            current.on_job_status(data)
        status = data.get('status', '')
        if status == 'completed':
            self.tray.showMessage(
                '打印完成',
                f'任务 #{data["job_id"]} 已完成',
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self._notifications.show_notification(f'任务 #{data["job_id"]} 打印完成', '#6B8F6B')
        elif status == 'failed':
            self.tray.showMessage(
                '打印失败',
                f'任务 #{data["job_id"]} 失败: {data.get("error", "")}',
                QSystemTrayIcon.MessageIcon.Critical,
                5000,
            )
            self._notifications.show_notification(f'任务 #{data["job_id"]} 失败', '#C53A3A')
        elif status == 'submitted':
            self._notifications.show_notification(f'任务 #{data["job_id"]} 已提交', '#8B7355')

    def _on_printer_status(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, 'on_printer_status'):
            current.on_printer_status(data)

    def _on_health_status(self, data: dict):
        queue_size = data.get('queue_size', 0)
        workers = data.get('workers', 0)
        self._last_queue_size = queue_size
        if self._server and self._server.is_running:
            self.status_text.setText(
                f'运行中 · 端口 {self._server.port} · 队列 {queue_size} · 工作进程 {workers}'
            )

    def closeEvent(self, event):
        self._state_manager.save()
        current_page = self.stack.currentWidget()
        if hasattr(current_page, 'history_table'):
            self._state_manager.save_table_state('history', current_page.history_table)
        if hasattr(current_page, 'cleanup'):
            current_page.cleanup()
        event.ignore()
        self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position notification stack in bottom-right
        nw = 320
        nh = self._notifications.sizeHint().height()
        self._notifications.setGeometry(self.width() - nw - 24, self.height() - nh - 60, nw, nh)


def run_gui(app, config, server_handle: ServerHandle):
    qapp = QApplication(sys.argv)
    # Set default font for Chinese character support on Windows
    font = QFont('Microsoft YaHei UI', 9)
    qapp.setFont(font)
    from gui.theme import ThemeEngine

    theme = ThemeEngine.instance()
    # Load persisted theme, default to light
    saved_theme = config.get('theme_mode', 'light')
    if saved_theme not in ('light', 'dark'):
        saved_theme = 'light'
    theme.apply(saved_theme, qapp)
    window = MainWindow(app, config, server_handle)
    qapp.aboutToQuit.connect(window._bridge.stop)
    qapp.exec()
