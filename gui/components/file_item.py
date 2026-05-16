"""Shared file-list item widget with thumbnail, path, and delete."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

IMAGE_EXTS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic', '.heif']


class FileItemWidget(QWidget):
    """A file list row: thumbnail, name, path, optional open button, delete button."""

    def __init__(
        self, file_path: str, list_widget: QListWidget, open_btn: bool = False, parent=None
    ):
        super().__init__(parent)
        self.file_path = file_path
        self._list_widget = list_widget
        self.setMinimumHeight(48)
        p = Path(file_path)
        lo = QHBoxLayout(self)
        lo.setContentsMargins(8, 4, 8, 4)
        lo.setSpacing(10)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if p.suffix.lower() in IMAGE_EXTS:
            pixmap = QPixmap(file_path)
            if not pixmap.isNull():
                thumb.setPixmap(pixmap.scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                thumb.setText('\U0001f5bc')
        else:
            thumb.setText('\U0001f4c4')
        lo.addWidget(thumb)

        # File name + truncated path
        parent_dir = p.parent.name if p.parent.name else p.parent.drive
        display_path = f'{parent_dir}\\{p.name}'
        if len(display_path) > 55:
            display_path = f'{parent_dir[0]}...\\{p.name}'
        info = QLabel(p.name)
        info.setToolTip(str(p))
        info.setStyleSheet('font-size: 12px; color: #8A8178;')

        path_lbl = QLabel(display_path)
        path_lbl.setToolTip(str(p))
        path_lbl.setStyleSheet('font-size: 11px; color: #6B7280;')

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.addWidget(info)
        text_col.addWidget(path_lbl)
        lo.addLayout(text_col, 1)

        if open_btn:
            btn = QPushButton('打开')
            btn.setFixedWidth(50)
            btn.setObjectName('ghost')
            btn.setProperty('compact', True)
            btn.clicked.connect(self._open_file)
            lo.addWidget(btn)

        del_btn = QPushButton('✕')
        del_btn.setFixedWidth(28)
        del_btn.setObjectName('ghostDanger')
        del_btn.setProperty('compact', True)
        del_btn.clicked.connect(self._delete_self)
        lo.addWidget(del_btn)

    def _open_file(self):
        import subprocess

        subprocess.Popen(['explorer', self.file_path], shell=True)

    def _delete_self(self):
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            w = self._list_widget.itemWidget(item)
            if w is self:
                self._list_widget.takeItem(i)
                break


def populate_file_list(list_widget: QListWidget, paths: list[str], open_btn: bool = False):
    """Clear and populate a QListWidget with FileItemWidget rows."""
    list_widget.clear()
    for p in paths:
        item = QListWidgetItem()
        w = FileItemWidget(p, list_widget, open_btn=open_btn)
        item.setSizeHint(w.sizeHint())
        list_widget.addItem(item)
        list_widget.setItemWidget(item, w)
    list_widget.setVisible(len(paths) > 0)


def collect_file_paths(list_widget: QListWidget) -> list[str]:
    """Collect file paths from a QListWidget populated by populate_file_list."""
    paths = []
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        w = list_widget.itemWidget(item)
        if w and hasattr(w, 'file_path'):
            paths.append(w.file_path)
    return paths
