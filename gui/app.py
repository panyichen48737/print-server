"""MainWindow: SidebarWidget + QStackedWidget + system tray."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMenu,
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
        self._idle_timer = None

        # EventBridge — thread-safe EventBus to Qt signal bridge
        self._bridge = EventBridge(self._event_bus, self)
        self._bridge.job_status.connect(self._on_job_status)
        self._bridge.printer_status.connect(self._on_printer_status)
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

        # System tray
        self._setup_tray()

        # Health timer (started on first show, stopped when hidden)
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._refresh_status)

        # Window state persistence
        from gui.settings_store import WindowStateManager

        self._state_manager = WindowStateManager(self)
        self._state_manager.restore()

        # Select first page
        self.sidebar.setCurrentRow(0)

        # Position notification stack bottom-right
        self._notifications.raise_()

        # Register with watchdog for crash recovery
        QTimer.singleShot(3000, self._register_watchdog)

        # Auto-update check (deferred to avoid delaying startup)
        auto_enabled = self._config.get('auto_update_check', True) if self._config else True
        if auto_enabled:
            QTimer.singleShot(8000, self._check_auto_update)

        # Check if service already has a pre-downloaded update
        QTimer.singleShot(10000, self._check_service_pending)

        # Check Quark API configuration on startup
        QTimer.singleShot(2000, self._check_quark_config)

    def show_notification(self, text: str, color: str = '#8B7355'):
        self._notifications.show_notification(text, color)

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
        from gui.pipe_client import shutdown as wd_shutdown

        wd_shutdown()
        if self._server:
            self._server.stop()
        QApplication.quit()

    def _register_watchdog(self):
        """Register with watchdog service for crash recovery."""
        port = self._server.port if self._server else 5000
        from gui.pipe_client import register as wd_register

        wd_register(port)

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
            self._idle_timer.start(15000)

    def _check_quark_config(self):
        """Check Quark API config on startup and warn if missing."""
        if not self._config:
            return
        key_id = self._config.get('quark_api_key_id', '')
        key_secret = self._config.get('quark_api_key', '')
        if not key_id or not key_secret:
            self.tray.showMessage(
                '夸克 API 未配置',
                '图片打印和文档扫描需要 API 密钥，请前往设置页面配置',
                QSystemTrayIcon.MessageIcon.Warning,
                8000,
            )
            self.show_notification('夸克 API 未配置 - 图片打印和文档扫描将无法使用', '#C53A3A')

    def _check_idle_and_apply(self):
        """Auto-apply update when server is idle (no active jobs)."""
        if not self._server or not self._server.is_running:
            return
        if not getattr(self, '_service_pending_update', None):
            return
        # Check queue is empty
        repo = getattr(self._app.state, 'job_repo', None)
        stats = repo.get_stats() if repo else {}
        if stats.get('queued', 0) > 0 or stats.get('printing', 0) > 0:
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
        running = self._server and self._server.is_running
        if running:
            self.sidebar.set_server_status(True, self._server.port)
        else:
            self.sidebar.set_server_status(False)

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
        overall = data.get('overall', '')
        name = data.get('name', '未知')
        if overall == 'error':
            self.tray.showMessage(
                '打印机错误',
                f'{name} 异常，请检查打印机状态',
                QSystemTrayIcon.MessageIcon.Critical,
                5000,
            )
        elif overall == 'offline':
            self.tray.showMessage(
                '打印机离线',
                f'{name} 已断开连接',
                QSystemTrayIcon.MessageIcon.Critical,
                5000,
            )
        elif overall == 'warning':
            self.tray.showMessage(
                '打印机警告',
                f'{name} 状态异常',
                QSystemTrayIcon.MessageIcon.Information,
                3000,
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

    def hideEvent(self, event):
        super().hideEvent(event)
        self._health_timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._health_timer.isActive():
            self._health_timer.start(3000)
            self._refresh_status()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position notification stack in bottom-right
        nw = 320
        nh = self._notifications.sizeHint().height()
        self._notifications.setGeometry(self.width() - nw - 24, self.height() - nh - 60, nw, nh)


def run_gui(app, config, server_handle: ServerHandle):
    qapp = QApplication.instance() or QApplication(sys.argv)
    from launcher import _install_qt_translator

    _install_qt_translator()
    from gui.theme import ThemeEngine

    theme = ThemeEngine.instance()
    # Load persisted theme, default to light
    saved_theme = config.get('theme_mode', 'light')
    if saved_theme not in ('light', 'dark'):
        saved_theme = 'light'
    theme.apply(saved_theme, qapp)
    window = MainWindow(app, config, server_handle)
    qapp.aboutToQuit.connect(window._bridge.stop)
    # --tray: auto-start (registry), only show tray icon
    if '--tray' not in sys.argv:
        window.show()
    qapp.exec()
