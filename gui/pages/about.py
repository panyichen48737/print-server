"""About page: version info, build manifest, update check/download/install."""
from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app._paths import config_dir, persistent_dir
from app.updater import UpdateInfo, check_latest_version, download_installer, install_update
from app.version import __build_date__, __pyinstaller_version__, __version__, get_build_manifest


class _UpdateCheckWorker(QObject):
    """Background worker for update operations. Runs on a QThread."""

    check_finished = Signal(object)  # UpdateInfo | None
    download_progress = Signal(int, int)  # downloaded, total
    download_finished = Signal(bool)  # success
    install_launched = Signal(bool)

    @Slot()
    def run_check(self):
        info = check_latest_version()
        self.check_finished.emit(info)

    @Slot(str, str)
    def run_download(self, url: str, dest: str):
        success = download_installer(url, Path(dest), self._on_progress)
        self.download_finished.emit(success)

    def _on_progress(self, downloaded: int, total: int):
        self.download_progress.emit(downloaded, total)

    @Slot(str)
    def run_install(self, installer_path: str):
        ok = install_update(Path(installer_path))
        self.install_launched.emit(ok)


class _ToggleSection(QWidget):
    """Collapsible section with a header button."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle = QPushButton(f"▶ {title}")
        self.toggle.setObjectName("ghost")
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setStyleSheet("QPushButton { font-size: 12px; padding: 6px 12px; text-align: left; }")
        self.toggle.clicked.connect(self._toggle)

        self.body = QWidget()
        self.body.setVisible(False)

        layout.addWidget(self.toggle)
        layout.addWidget(self.body)

    def _toggle(self):
        expanded = not self.body.isVisible()
        self.body.setVisible(expanded)
        self.toggle.setText(f"{'▼' if expanded else '▶'} {self.toggle.text()[2:]}")


class AboutPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._update_info: UpdateInfo | None = None
        self._installer_path: Path | None = None
        self._update_thread: QThread | None = None
        self._update_worker: _UpdateCheckWorker | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("dashboardScroll")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 28, 32, 28)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(8)

        # ── Header ──
        title = QLabel("iOS 云打印服务器")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(f"版本 {__version__}")
        version.setStyleSheet("font-size: 16px; color: #8A8178;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        desc = QLabel("Windows 打印服务器，接收 iOS Scriptable 和 Web 请求，"
                       "通过 pywin32 驱动本地打印机。")
        desc.setWordWrap(True)
        desc.setMaximumWidth(400)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 13px; color: #8A8178;")
        layout.addWidget(desc)

        # ── GitHub link ──
        links = QHBoxLayout()
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github_btn = QPushButton("GitHub")
        github_btn.setObjectName("ghost")
        github_btn.setProperty("compact", True)
        github_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/panyichen48737/print-server")
        )
        links.addWidget(github_btn)
        layout.addLayout(links)

        layout.addSpacing(12)

        # ── Build info card ──
        manifest = get_build_manifest()
        tools = manifest.get('build_tools', {})

        info_card = QWidget()
        info_card.setObjectName("statCard")
        info_card.setStyleSheet("""
            QWidget#statCard { padding: 16px 20px; }
        """)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 16, 20, 16)
        info_layout.setSpacing(6)

        heading = QLabel("构建信息")
        heading.setObjectName("sectionHeading")
        info_layout.addWidget(heading)

        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(16)

        row = 0

        def add_row(label, value, link_url=None):
            nonlocal row
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 12px; color: #9A928A; font-weight: 500;")
            if link_url and value:
                val = QLabel(f'<a href="{link_url}" style="color: #B8956A; font-family: Consolas, monospace; font-size: 12px; text-decoration: none;">{value}</a>')
                val.setOpenExternalLinks(True)
            else:
                val = QLabel(str(value) if value else '—')
                val.setStyleSheet("font-size: 12px; color: #E8E5E0; font-family: Consolas, monospace;")
                val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(val, row, 1, Qt.AlignmentFlag.AlignRight)
            row += 1

        add_row("构建日期", __build_date__)
        add_row("Python", tools.get('python'))
        add_row("uv", tools.get('uv'))

        # Commit SHA as link
        commit = manifest.get('commit_sha')
        gh = manifest.get('github', {})
        repo = gh.get('repo', '')
        server = gh.get('server_url', 'https://github.com')
        commit_url = f"{server}/{repo}/commit/{commit}" if commit and repo else None
        add_row("Commit", commit[:10] + "…" if commit and len(commit) > 10 else commit, commit_url)

        # CI Run ID as link
        run_id = gh.get('run_id', '')
        run_url = f"{server}/{repo}/actions/runs/{run_id}" if run_id and repo else None
        add_row("构建编号", f"#{run_id}" if run_id else None, run_url)

        add_row("PyInstaller", __pyinstaller_version__)

        info_layout.addLayout(grid)

        pkgs = manifest.get('pip_packages', {})
        if pkgs:
            self._build_pkg_section(info_layout, pkgs)

        layout.addWidget(info_card, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Update section ──
        self.update_btn = QPushButton("检查更新")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._check_update)
        layout.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        self.update_progress.setFixedHeight(6)
        self.update_progress.setTextVisible(False)
        layout.addWidget(self.update_progress)

        self.update_status = QLabel("")
        self.update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.update_status)

        # ── Other actions ──
        action_row = QHBoxLayout()
        action_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_row.setSpacing(10)

        log_btn = QPushButton("日志文件夹")
        log_btn.setObjectName("ghost")
        log_btn.setProperty("compact", True)
        log_btn.clicked.connect(self._open_log_folder)
        action_row.addWidget(log_btn)

        cfg_btn = QPushButton("配置文件")
        cfg_btn.setObjectName("ghost")
        cfg_btn.setProperty("compact", True)
        cfg_btn.clicked.connect(self._open_config_folder)
        action_row.addWidget(cfg_btn)

        layout.addLayout(action_row)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

    def _build_pkg_section(self, parent_layout, pkgs: dict):
        """Add collapsible pip package list."""
        section = _ToggleSection(f"已安装 {len(pkgs)} 个 Python 包")
        body_layout = QVBoxLayout(section.body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(1)

        sorted_pkgs = sorted(pkgs.items())
        for name, ver in sorted_pkgs:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            n = QLabel(name)
            n.setStyleSheet("font-size: 11px; color: #9A928A;")
            n.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v = QLabel(ver)
            v.setStyleSheet("font-size: 11px; color: #E8E5E0; font-family: Consolas, monospace;")
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(n, 1)
            row.addWidget(v, 0)
            body_layout.addLayout(row)

        parent_layout.addWidget(section)

    def _open_log_folder(self):
        log_dir = Path(persistent_dir()) / "logs"
        if log_dir.exists():
            subprocess.Popen(["explorer", str(log_dir)], shell=True)

    def _open_config_folder(self):
        cfg_dir = Path(config_dir())
        if cfg_dir.exists():
            subprocess.Popen(["explorer", str(cfg_dir)], shell=True)

    # ── Update flow ──

    def _start_worker(self, mode: str):
        self._cleanup_thread()
        self._update_thread = QThread(self)
        self._update_worker = _UpdateCheckWorker()
        self._update_worker.moveToThread(self._update_thread)

        if mode == "check":
            self._update_worker.check_finished.connect(self._on_check_finished)
            self._update_thread.started.connect(self._update_worker.run_check)
            self._update_thread.start()
        elif mode == "download":
            url = self._update_info.download_url if self._update_info else None
            dest = str(self._installer_path) if self._installer_path else ""
            if not url or not dest:
                self._on_download_finished(False)
                return
            self._update_worker.download_progress.connect(self._on_download_progress)
            self._update_worker.download_finished.connect(self._on_download_finished)
            self._update_thread.started.connect(
                lambda: self._update_worker.run_download(url, dest)
            )
            self._update_thread.start()
        elif mode == "install":
            dest = str(self._installer_path) if self._installer_path else ""
            self._update_worker.install_launched.connect(self._on_install_launched)
            self._update_thread.started.connect(
                lambda: self._update_worker.run_install(dest)
            )
            self._update_thread.start()

    def _cleanup_thread(self):
        if self._update_thread and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait(2000)
        self._update_thread = None
        self._update_worker = None

    def _check_update(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("检查中...")
        self.update_progress.setVisible(False)
        self.update_status.setStyleSheet("color: #8A8178;")
        self.update_status.setText("正在检查更新...")

        # Reset previous download state
        self._update_info = None
        self._installer_path = None

        self._start_worker("check")

    def _on_check_finished(self, info: UpdateInfo | None):
        self._cleanup_thread()
        self.update_btn.setEnabled(True)
        self.update_btn.setText("检查更新")

        if info is None:
            self.update_status.setText("检查更新失败，请稍后重试")
            self.update_status.setStyleSheet("color: #C53A3A;")
            self.update_btn.setText("重试")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(self._check_update)
            return

        self._update_info = info

        if not info.is_newer:
            self.update_status.setText(f"✅ 已是最新版本 (v{__version__})")
            self.update_status.setStyleSheet("color: #6B8F6B;")
            return

        self.update_status.setText(f"新版本 v{info.latest_version} 可用")
        self.update_status.setStyleSheet("color: #B8956A;")

        if info.download_url:
            self.update_btn.setText("下载更新")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(self._start_download)
            self.update_btn.setEnabled(True)
        else:
            self.update_btn.setText("前往下载页")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(
                lambda: webbrowser.open(info.release_url)
            )
            self.update_btn.setEnabled(True)

    def _start_download(self):
        cache_dir = persistent_dir() / "update_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)

        is_incremental = self._update_info and self._update_info.download_type == "incremental"
        if is_incremental:
            self._installer_path = (
                cache_dir / f"update-{self._update_info.latest_version}.zip"
            )
        else:
            self._installer_path = (
                cache_dir / f"iOSPrintServer-Setup-{self._update_info.latest_version}.exe"
            )

        self.update_btn.setEnabled(False)
        self.update_btn.setText("准备下载...")
        self.update_progress.setVisible(True)
        self.update_progress.setValue(0)

        self._start_worker("download")

    def _on_download_progress(self, downloaded: int, total: int):
        self.update_progress.setVisible(True)
        self.update_progress.setMaximum(total)
        self.update_progress.setValue(downloaded)
        mb_d = downloaded / 1024 / 1024
        mb_t = total / 1024 / 1024
        pct = int(downloaded * 100 / total) if total else 0
        self.update_status.setText(f"下载中... {mb_d:.1f}/{mb_t:.1f} MB ({pct}%)")

    def _on_download_finished(self, success: bool):
        self._cleanup_thread()
        self.update_progress.setVisible(False)

        if not success:
            self.update_status.setText("下载失败，请重试")
            self.update_status.setStyleSheet("color: #C53A3A;")
            self.update_btn.setText("重试")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(self._start_download)
            self.update_btn.setEnabled(True)
            if self._installer_path and self._installer_path.exists():
                self._installer_path.unlink(missing_ok=True)
            return

        self.update_status.setText("下载完成！正在安装...")
        self.update_status.setStyleSheet("color: #6B8F6B;")
        self.update_btn.setEnabled(False)
        self.update_btn.setText("安装中...")

        # Route based on download type
        if self._update_info and self._update_info.download_type == "incremental":
            self._apply_incremental_update()
        else:
            self._start_worker("install")

    def _apply_incremental_update(self):
        """Send update zip to service for atomic replacement."""
        from gui.pipe_client import apply_update, service_status
        import sys
        import os

        # Check service is running
        status = service_status()
        if status is None:
            self.update_status.setText("更新服务未运行，请使用安装器手动更新")
            self.update_status.setStyleSheet("color: #C53A3A;")
            self.update_btn.setText("下载安装器")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(self._switch_to_full_download)
            self.update_btn.setEnabled(True)
            return

        app_dir = self._get_app_dir()

        resp = apply_update(str(self._installer_path), app_dir)
        if resp is None or resp.status != "ok":
            self.update_status.setText("更新服务响应失败，请重试")
            self.update_status.setStyleSheet("color: #C53A3A;")
            self.update_btn.setText("重试")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(self._apply_incremental_update)
            self.update_btn.setEnabled(True)
            return

        self.update_status.setText("更新提交成功，程序即将重启...")
        self.update_status.setStyleSheet("color: #6B8F6B;")

        # Exit — service will wait, replace _internal/, and restart
        QTimer.singleShot(1000, lambda: os._exit(0))

    def _switch_to_full_download(self):
        """Fallback: download full installer instead."""
        if self._update_info and self._update_info.release_url:
            import webbrowser
            webbrowser.open(self._update_info.release_url)
            self.update_status.setText("请在浏览器中下载安装器")
            self.update_btn.setText("检查更新")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(self._check_update)
            self.update_btn.setEnabled(True)

    def _get_app_dir(self) -> str | None:
        """Detect installation directory."""
        import sys
        from pathlib import Path
        if getattr(sys, 'frozen', False):
            return str(Path(sys.executable).parent)
        return None

    def _on_install_launched(self, success: bool):
        self._cleanup_thread()
        if not success:
            self.update_status.setText("安装启动失败，请手动下载")
            self.update_status.setStyleSheet("color: #C53A3A;")
            self.update_btn.setText("前往下载页")
            self.update_btn.clicked.disconnect()
            self.update_btn.clicked.connect(
                lambda: webbrowser.open(self._update_info.release_url)
            )
            self.update_btn.setEnabled(True)

    def cleanup(self):
        """Stop pending thread when page is destroyed."""
        self._cleanup_thread()