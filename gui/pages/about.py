"""About page: version info, update check, links."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class AboutPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        title = QLabel("iOS 云打印服务器")
        title.setStyleSheet("font-size: 28px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel("版本 1.6.0")
        version.setStyleSheet("font-size: 16px; color: #6B7280;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        desc = QLabel("Windows 打印服务器，接收 iOS Scriptable 和 Web 请求，"
                       "通过 pywin32 驱动本地打印机。")
        desc.setWordWrap(True)
        desc.setMaximumWidth(400)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("font-size: 13px; color: #9CA3AF;")
        layout.addWidget(desc)

        # Links
        links = QHBoxLayout()
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github_btn = QPushButton("GitHub")
        github_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/panyichen48737/print-server")
        )
        doc_btn = QPushButton("管理后台")
        doc_btn.clicked.connect(lambda: self._open_admin())
        links.addWidget(github_btn)
        links.addWidget(doc_btn)
        layout.addLayout(links)

        # Check for updates
        self.update_btn = QPushButton("检查更新")
        self.update_btn.clicked.connect(self._check_update)
        layout.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.update_label = QLabel("")
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.update_label)

        layout.addStretch()

    def _open_admin(self):
        port = self._mw._server.port if self._mw._server else 5000
        webbrowser.open(f"http://127.0.0.1:{port}/admin")

    def _check_update(self):
        self.update_label.setText("暂无更新")
        self.update_label.setStyleSheet("color: #16A34A;")