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

    def save_table_state(self, table_key: str, table):
        """Save column widths and sort for a table."""
        from PySide6.QtCore import Qt
        widths = [table.columnWidth(i) for i in range(table.model().columnCount())]
        self._settings.setValue(f"table_{table_key}", widths)
        sort_col = table.horizontalHeader().sortIndicatorSection()
        sort_order = table.horizontalHeader().sortIndicatorOrder()
        self._settings.setValue(f"table_{table_key}_sort_col", sort_col)
        self._settings.setValue(f"table_{table_key}_sort_order", int(sort_order))

    def restore_table_state(self, table_key: str, table):
        """Restore column widths and sort for a table."""
        from PySide6.QtCore import Qt
        widths = self._settings.value(f"table_{table_key}")
        if widths and isinstance(widths, list):
            for i, w in enumerate(widths):
                if i < table.model().columnCount():
                    table.setColumnWidth(i, int(w))
        sort_col = self._settings.value(f"table_{table_key}_sort_col", -1, type=int)
        if sort_col >= 0:
            sort_order_val = self._settings.value(f"table_{table_key}_sort_order", 0, type=int)
            sort_order = Qt.SortOrder.AscendingOrder if sort_order_val == 0 else Qt.SortOrder.DescendingOrder
            table.sortByColumn(sort_col, sort_order)