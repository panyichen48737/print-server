"""Update section widget: version check, download, and install."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from app.core._paths import persistent_dir
from app.core.version import __version__
from app.updater import UpdateInfo, check_latest_version, download_installer, install_update


class _UpdateCheckWorker(QObject):
    check_finished = Signal(object)
    download_progress = Signal(int, int)
    download_finished = Signal(bool)
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


class UpdateSection(QWidget):
    """Self-contained update check/download/install widget."""

    @staticmethod
    def _safe_disconnect(signal):
        """断开信号连接，无连接时不抛异常"""
        import contextlib

        with contextlib.suppress(TypeError, RuntimeError):
            signal.disconnect()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._update_info: UpdateInfo | None = None
        self._installer_path: Path | None = None
        self._update_thread: QThread | None = None
        self._update_worker: _UpdateCheckWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        self.update_btn = QPushButton('检查更新')
        self.update_btn.setObjectName('primary')
        self.update_btn.clicked.connect(self._check_update)
        layout.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.update_progress = QProgressBar()
        self.update_progress.setVisible(False)
        self.update_progress.setFixedHeight(6)
        self.update_progress.setTextVisible(False)
        layout.addWidget(self.update_progress)

        self.update_status = QLabel('')
        self.update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._spinner_label = QLabel('')
        self._spinner_label.setVisible(False)
        self._spinner_label.setStyleSheet('font-size: 16px; color: #B8956A;')
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._advance_spinner)
        self._spinner_frames = ['◜', '◝', '◞', '◟']
        self._spinner_idx = 0

        status_row = QHBoxLayout()
        status_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_row.setSpacing(6)
        status_row.addStretch()
        status_row.addWidget(self._spinner_label)
        status_row.addWidget(self.update_status)
        status_row.addStretch()
        layout.addLayout(status_row)

    # ── Worker lifecycle ──

    def _start_worker(self, mode: str):
        self._cleanup_thread()
        self._update_thread = QThread(self)
        self._update_worker = _UpdateCheckWorker()
        self._update_worker.moveToThread(self._update_thread)

        if mode == 'check':
            self._update_worker.check_finished.connect(self._on_check_finished)
            self._update_thread.started.connect(self._update_worker.run_check)
            self._update_thread.start()
        elif mode == 'download':
            url = self._update_info.download_url if self._update_info else None
            dest = str(self._installer_path) if self._installer_path else ''
            if not url or not dest:
                self._on_download_finished(False)
                return
            self._update_worker.download_progress.connect(self._on_download_progress)
            self._update_worker.download_finished.connect(self._on_download_finished)
            self._update_thread.started.connect(lambda: self._update_worker.run_download(url, dest))
            self._update_thread.start()
        elif mode == 'install':
            dest = str(self._installer_path) if self._installer_path else ''
            self._update_worker.install_launched.connect(self._on_install_launched)
            self._update_thread.started.connect(lambda: self._update_worker.run_install(dest))
            self._update_thread.start()

    def _cleanup_thread(self):
        if self._update_thread and self._update_thread.isRunning():
            self._update_thread.quit()
            self._update_thread.wait(2000)
        self._update_thread = None
        self._update_worker = None

    # ── Update check ──

    def _check_update(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText('检查中...')
        self.update_progress.setVisible(False)
        self.update_status.setStyleSheet('color: #8A8178;')
        self.update_status.setText('正在检查更新...')
        self._start_spinner()
        self._update_info = None
        self._installer_path = None
        self._start_worker('check')

    def _on_check_finished(self, info: UpdateInfo | None):
        self._stop_spinner()
        self._cleanup_thread()
        self.update_btn.setEnabled(True)
        self.update_btn.setText('检查更新')

        if info is None:
            self.update_status.setText('检查更新失败，请稍后重试')
            self.update_status.setStyleSheet('color: #C53A3A;')
            self.update_btn.setText('重试')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(self._check_update)
            return

        self._update_info = info

        if not info.is_newer:
            self.update_status.setText(f'✅ 已是最新版本 (v{__version__})')
            self.update_status.setStyleSheet('color: #6B8F6B;')
            return

        self.update_status.setText(f'新版本 v{info.latest_version} 可用')
        self.update_status.setStyleSheet('color: #B8956A;')

        if info.download_url:
            self.update_btn.setText('下载更新')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(self._start_download)
            self.update_btn.setEnabled(True)
        else:
            import webbrowser

            self.update_btn.setText('前往下载页')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(lambda: webbrowser.open(info.release_url))
            self.update_btn.setEnabled(True)

    # ── Download ──

    def _start_download(self):
        cache_dir = persistent_dir() / 'update_cache'
        cache_dir.mkdir(parents=True, exist_ok=True)

        is_incremental = self._update_info and self._update_info.download_type == 'incremental'
        if is_incremental:
            self._installer_path = cache_dir / f'update-{self._update_info.latest_version}.zip'
        else:
            self._installer_path = (
                cache_dir / f'iOSPrintServer-Setup-{self._update_info.latest_version}.exe'
            )

        self.update_btn.setEnabled(False)
        self.update_btn.setText('准备下载...')
        self.update_progress.setVisible(True)
        self.update_progress.setValue(0)
        self._start_worker('download')

    def _on_download_progress(self, downloaded: int, total: int):
        self.update_progress.setVisible(True)
        self.update_progress.setMaximum(total)
        self.update_progress.setValue(downloaded)
        mb_d = downloaded / 1024 / 1024
        mb_t = total / 1024 / 1024
        pct = int(downloaded * 100 / total) if total else 0
        self.update_status.setText(f'下载中... {mb_d:.1f}/{mb_t:.1f} MB ({pct}%)')

    def _on_download_finished(self, success: bool):
        self._cleanup_thread()
        self.update_progress.setVisible(False)

        if not success:
            self.update_status.setText('下载失败，请重试')
            self.update_status.setStyleSheet('color: #C53A3A;')
            self.update_btn.setText('重试')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(self._start_download)
            self.update_btn.setEnabled(True)
            if self._installer_path and self._installer_path.exists():
                self._installer_path.unlink(missing_ok=True)
            return

        self.update_status.setText('下载完成！正在安装...')
        self.update_status.setStyleSheet('color: #6B8F6B;')
        self.update_btn.setEnabled(False)
        self.update_btn.setText('安装中...')

        if self._update_info and self._update_info.download_type == 'incremental':
            self._apply_go_update()
        else:
            self._start_worker('install')

    def _apply_go_update(self):
        """Apply incremental update via Go service, or full installer via NSIS."""
        from gui.pipe_client import apply_update, read_pending_file, service_status

        # Check if Go already downloaded the update
        go_pending = read_pending_file()
        installer_path = self._installer_path

        if go_pending and go_pending.download_type == 'full':
            # Full installer already downloaded by Go — exec NSIS directly
            import subprocess

            subprocess.Popen(
                [go_pending.zip_path, '/S'],
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            self.update_status.setText('更新提交成功，程序即将重启...')
            self.update_status.setStyleSheet('color: #6B8F6B;')
            QTimer.singleShot(1000, lambda: os._exit(0))
            return

        if go_pending and go_pending.zip_path:
            # Reuse Go-downloaded file
            installer_path = Path(go_pending.zip_path)

        if not installer_path or not installer_path.exists():
            import webbrowser

            self.update_status.setText('更新文件丢失，请重新下载')
            self.update_status.setStyleSheet('color: #C53A3A;')
            self.update_btn.setText('前往下载页')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(
                lambda: (
                    webbrowser.open(self._update_info.release_url) if self._update_info else None
                )
            )
            self.update_btn.setEnabled(True)
            return

        status = service_status()
        if status is None:
            import webbrowser

            self.update_status.setText('更新服务未运行，请使用安装器手动更新')
            self.update_status.setStyleSheet('color: #C53A3A;')
            self.update_btn.setText('前往下载页')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(
                lambda: (
                    webbrowser.open(self._update_info.release_url) if self._update_info else None
                )
            )
            self.update_btn.setEnabled(True)
            return

        import sys

        app_dir = str(Path(sys.executable).parent) if getattr(sys, 'frozen', False) else None
        if not app_dir:
            self.update_status.setText('无法确定安装目录')
            self.update_status.setStyleSheet('color: #C53A3A;')
            return

        resp = apply_update(str(installer_path), app_dir)
        if resp is None or resp.status != 'ok':
            self.update_status.setText('更新服务响应失败，请重试')
            self.update_status.setStyleSheet('color: #C53A3A;')
            self.update_btn.setText('重试')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(self._apply_go_update)
            self.update_btn.setEnabled(True)
            return

        self.update_status.setText('更新提交成功，程序即将重启...')
        self.update_status.setStyleSheet('color: #6B8F6B;')
        QTimer.singleShot(1000, lambda: os._exit(0))

    def _on_install_launched(self, success: bool):
        self._cleanup_thread()
        if not success:
            import webbrowser

            self.update_status.setText('安装启动失败，请手动下载')
            self.update_status.setStyleSheet('color: #C53A3A;')
            self.update_btn.setText('前往下载页')
            self._safe_disconnect(self.update_btn.clicked)
            self.update_btn.clicked.connect(
                lambda: (
                    webbrowser.open(self._update_info.release_url) if self._update_info else None
                )
            )
            self.update_btn.setEnabled(True)

    # ── Spinner ──

    def _advance_spinner(self):
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        self._spinner_label.setText(self._spinner_frames[self._spinner_idx])

    def _start_spinner(self):
        self._spinner_idx = 0
        self._spinner_label.setText(self._spinner_frames[0])
        self._spinner_label.setVisible(True)
        self._spinner_timer.start(200)

    def _stop_spinner(self):
        self._spinner_timer.stop()
        self._spinner_label.setVisible(False)
        self._spinner_label.setText('')

    def cleanup(self):
        """Stop pending thread when page is destroyed."""
        self._stop_spinner()
        self._cleanup_thread()
