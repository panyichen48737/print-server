"""About page: version info, build manifest, update check/download/install."""

from __future__ import annotations

import subprocess
import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core._paths import config_dir
from app.core.version import (
    __build_date__,
    __pyinstaller_version__,
    __version__,
    get_build_manifest,
)
from gui.components.page_base import PageBase
from gui.pages.update import UpdateSection


class _ToggleSection(QWidget):
    """Collapsible section with a header button."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toggle = QPushButton(f'▶ {title}')
        self.toggle.setObjectName('ghost')
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setStyleSheet(
            'QPushButton { font-size: 12px; padding: 6px 12px; text-align: left; }'
        )
        self.toggle.clicked.connect(self._toggle)

        self.body = QWidget()
        self.body.setVisible(False)

        layout.addWidget(self.toggle)
        layout.addWidget(self.body)

    def _toggle(self):
        expanded = not self.body.isVisible()
        self.body.setVisible(expanded)
        self.toggle.setText(f'{"▼" if expanded else "▶"} {self.toggle.text()[2:]}')


class AboutPage(PageBase):
    def __init__(self, main_window, parent=None):
        self._mw = main_window
        super().__init__(parent)

        self.update_section = UpdateSection()
        self._build_content(self._content)

    def _build_content(self, layout: QVBoxLayout):
        title = QLabel('iOS 云打印服务器')
        title.setObjectName('pageTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        version = QLabel(f'版本 {__version__}')
        version.setStyleSheet('font-size: 16px; color: #8A8178;')
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)

        desc = QLabel(
            'Windows 打印服务器，接收 iOS Scriptable 和 Web 请求，通过 pywin32 驱动本地打印机。'
        )
        desc.setWordWrap(True)
        desc.setMaximumWidth(400)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet('font-size: 13px; color: #8A8178;')
        layout.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)

        links = QHBoxLayout()
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github_btn = QPushButton('GitHub')
        github_btn.setObjectName('ghost')
        github_btn.setProperty('compact', True)
        github_btn.clicked.connect(
            lambda: webbrowser.open('https://github.com/panyichen48737/print-server')
        )
        links.addWidget(github_btn)
        layout.addLayout(links)

        layout.addSpacing(12)

        manifest = get_build_manifest()
        tools = manifest.get('build_tools', {})

        info_card = QWidget()
        info_card.setObjectName('statCard')
        info_card.setStyleSheet("""
            QWidget#statCard { padding: 16px 20px; }
        """)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(20, 16, 20, 16)
        info_layout.setSpacing(6)

        heading = QLabel('构建信息')
        heading.setObjectName('sectionHeading')
        info_layout.addWidget(heading)

        grid = QGridLayout()
        grid.setVerticalSpacing(6)
        grid.setHorizontalSpacing(16)

        row = 0

        def add_row(label, value, link_url=None):
            nonlocal row
            lbl = QLabel(label)
            lbl.setStyleSheet('font-size: 12px; color: #9A928A; font-weight: 500;')
            if link_url and value:
                val = QLabel(
                    f'<a href="{link_url}" style="color: #B8956A; font-family: Consolas, monospace; font-size: 12px; text-decoration: none;">{value}</a>'
                )
                val.setOpenExternalLinks(True)
            else:
                val = QLabel(str(value) if value else '—')
                val.setStyleSheet(
                    'font-size: 12px; color: #E8E5E0; font-family: Consolas, monospace;'
                )
                val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(val, row, 1, Qt.AlignmentFlag.AlignRight)
            row += 1

        add_row('构建日期', __build_date__)
        add_row('Python', tools.get('python'))
        add_row('uv', tools.get('uv'))

        commit = manifest.get('commit_sha')
        gh = manifest.get('github', {})
        repo = gh.get('repo', '')
        server = gh.get('server_url', 'https://github.com')
        commit_url = f'{server}/{repo}/commit/{commit}' if commit and repo else None
        add_row('Commit', commit[:10] + '…' if commit and len(commit) > 10 else commit, commit_url)

        run_id = gh.get('run_id', '')
        run_url = f'{server}/{repo}/actions/runs/{run_id}' if run_id and repo else None
        add_row('构建编号', f'#{run_id}' if run_id else None, run_url)

        add_row('PyInstaller', __pyinstaller_version__)

        info_layout.addLayout(grid)

        pkgs = manifest.get('pip_packages', {})
        if pkgs:
            self._build_pkg_section(info_layout, pkgs)

        layout.addWidget(info_card, alignment=Qt.AlignmentFlag.AlignCenter)

        # Update section
        layout.addWidget(self.update_section)

        action_row = QHBoxLayout()
        action_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_row.setSpacing(10)

        log_btn = QPushButton('日志文件夹')
        log_btn.setObjectName('ghost')
        log_btn.setProperty('compact', True)
        log_btn.clicked.connect(self._open_log_folder)
        action_row.addWidget(log_btn)

        cfg_btn = QPushButton('配置文件')
        cfg_btn.setObjectName('ghost')
        cfg_btn.setProperty('compact', True)
        cfg_btn.clicked.connect(self._open_config_folder)
        action_row.addWidget(cfg_btn)

        layout.addLayout(action_row)

    def _build_pkg_section(self, parent_layout, pkgs: dict):
        section = _ToggleSection(f'已安装 {len(pkgs)} 个 Python 包')
        body_layout = QVBoxLayout(section.body)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(1)

        sorted_pkgs = sorted(pkgs.items())
        for name, ver in sorted_pkgs:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            n = QLabel(name)
            n.setStyleSheet('font-size: 11px; color: #9A928A;')
            n.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v = QLabel(ver)
            v.setStyleSheet('font-size: 11px; color: #E8E5E0; font-family: Consolas, monospace;')
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(n, 1)
            row.addWidget(v, 0)
            body_layout.addLayout(row)

        parent_layout.addWidget(section)

    def _open_log_folder(self):
        from app.core._paths import log_dir

        ld = log_dir()
        if ld.exists():
            subprocess.Popen(['explorer', str(ld)], shell=True)

    def _open_config_folder(self):
        cfg_dir = Path(config_dir())
        if cfg_dir.exists():
            subprocess.Popen(['explorer', str(cfg_dir)], shell=True)

    def cleanup(self):
        self.update_section.cleanup()
