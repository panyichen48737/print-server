"""About page: version info, update check, links."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.version import __build_date__, __pyinstaller_version__, __version__


class AboutPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        title = QLabel("iOS 云打印服务器")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(f"版本 {__version__}")
        version.setStyleSheet("font-size: 16px; color: #8A8178;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        build_info = QLabel(f"构建日期 {__build_date__}")
        build_info.setStyleSheet("font-size: 12px; color: #B0A89F;")
        build_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(build_info)

        pyinstaller_info = QLabel(f"PyInstaller {__pyinstaller_version__}")
        pyinstaller_info.setStyleSheet("font-size: 12px; color: #B0A89F;")
        pyinstaller_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(pyinstaller_info)

        desc = QLabel("Windows 打印服务器，接收 iOS Scriptable 和 Web 请求，"
                       "通过 pywin32 驱动本地打印机。")
        desc.setWordWrap(True)
        desc.setMaximumWidth(400)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 13px; color: #8A8178;")
        layout.addWidget(desc)

        # GitHub link
        links = QHBoxLayout()
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github_btn = QPushButton("GitHub")
        github_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/panyichen48737/print-server")
        )
        links.addWidget(github_btn)
        layout.addLayout(links)

        # Check for updates
        self.update_btn = QPushButton("检查更新")
        self.update_btn.clicked.connect(self._check_update)
        layout.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.update_label = QLabel("")
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.update_label)

        layout.addStretch()

    def _check_update(self):
        self.update_label.setText("暂无更新")
        self.update_label.setStyleSheet("color: #6B8F6B;")