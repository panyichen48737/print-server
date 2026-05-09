"""About page: version info, build manifest, links."""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.version import __build_date__, __pyinstaller_version__, __version__, get_build_manifest


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
        for label, value in [
            ("构建日期", __build_date__),
            ("Python", tools.get('python', '—')),
            ("uv", tools.get('uv', '—')),
            ("PyInstaller", __pyinstaller_version__),
            ("Commit", manifest.get('commit_sha', '—')),
        ]:
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 12px; color: #9A928A; font-weight: 500;")
            val = QLabel(str(value))
            val.setStyleSheet("font-size: 12px; color: #E8E5E0; font-family: Consolas, monospace;")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(val, row, 1, Qt.AlignmentFlag.AlignRight)
            row += 1

        info_layout.addLayout(grid)

        pkgs = manifest.get('pip_packages', {})
        if pkgs:
            self._build_pkg_section(info_layout, pkgs)

        layout.addWidget(info_card, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Check for updates ──
        self.update_btn = QPushButton("检查更新")
        self.update_btn.setObjectName("primary")
        self.update_btn.clicked.connect(self._check_update)
        layout.addWidget(self.update_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.update_label = QLabel("")
        self.update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.update_label)

        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

    def _build_pkg_section(self, parent_layout, pkgs: dict):
        """Add collapsible pip package list."""
        section = _ToggleSection(f"已安装 {len(pkgs)} 个 Python 包")
        body_layout = QVBoxLayout(section.body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(1)

        # Show in alphabetical order
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

    def _check_update(self):
        self.update_label.setText("暂无更新")
        self.update_label.setStyleSheet("color: #6B8F6B;")