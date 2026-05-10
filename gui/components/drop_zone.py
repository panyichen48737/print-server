"""Drag-and-drop zone for file selection — supports click to browse, multi-file, extension filter."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QFileDialog, QLabel, QVBoxLayout, QWidget

from app.core.config import Config


def _allowed_extensions() -> list[str]:
    try:
        return Config().get("allowed_extensions", [".pdf"])
    except Exception:
        return [".pdf"]


def _is_allowed(path: Path, extensions: list[str] | None = None) -> bool:
    exts = extensions if extensions is not None else _allowed_extensions()
    return path.suffix.lower() in exts


class DropZoneWidget(QWidget):
    files_selected = Signal(list)  # list of str paths

    def _update_style(self):
        from gui.theme import ThemeEngine
        t = ThemeEngine.instance().tokens
        self.setStyleSheet(f"""
            DropZoneWidget {{
                border: 2px dashed {t['outline']};
                border-radius: 12px;
                background-color: transparent;
            }}
            DropZoneWidget[drag_over="true"] {{
                border-color: {t['primary']};
                background-color: {t['surface_alt']};
            }}
        """)

    def __init__(self, parent=None, extensions: list[str] | None = None):
        super().__init__(parent)
        self._extensions = extensions
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self.setMaximumHeight(220)
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label = QLabel("📄")
        self._text_label = QLabel("点击选择文件，或拖拽到此处")
        self._info_label = QLabel("")
        self._info_label.setStyleSheet("background: transparent; color: #8A8178; font-size: 12px;")
        for lb in (self._icon_label, self._text_label, self._info_label):
            lb.setStyleSheet("background: transparent;")
        layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._text_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info_label, alignment=Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        exts = self._extensions or _allowed_extensions()
        patterns = " ".join(f"*{e}" for e in exts)
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            f"支持的文件 ({patterns});;所有文件 (*.*)",
        )
        if files:
            valid = [f for f in files if _is_allowed(Path(f), self._extensions)]
            if valid:
                self._update_info(valid)
                self.files_selected.emit(valid)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_over", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.exists() and _is_allowed(p, self._extensions):
                    paths.append(str(p))
            if paths:
                self._update_info(paths)
                self.files_selected.emit(paths)

    def _update_info(self, paths: list[str]):
        if len(paths) == 1:
            p = Path(paths[0])
            self._info_label.setText(f"{p.name} ({p.stat().st_size / 1024:.1f} KB)")
        else:
            total = sum(Path(f).stat().st_size for f in paths)
            self._info_label.setText(f"{len(paths)} 个文件（{total / 1024:.1f} KB）")
