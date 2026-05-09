"""Window state persistence via QSettings."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QMainWindow


class WindowStateManager:
    def __init__(self, window: QMainWindow):
        self._window = window
        self._settings = QSettings("iOSPrintServer", "main_window")

    def save(self):
        self._settings.setValue("geometry", self._window.saveGeometry())
        self._settings.setValue("last_page", self._window.sidebar.currentRow())

    def restore(self):
        geom = self._settings.value("geometry")
        if isinstance(geom, QByteArray):
            self._window.restoreGeometry(geom)
        page = self._settings.value("last_page", 0, type=int)
        if page is not None and 0 <= page < 7:
            self._window.sidebar.setCurrentRow(page)