"""Job manager page: queue + history tables with filter."""
from __future__ import annotations

from PySide6.QtCore import Qt, QAbstractTableModel
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableView, QVBoxLayout, QWidget,
)


class SimpleTableModel(QAbstractTableModel):
    """Read-only table model for job data."""
    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        self._headers = headers
        self._data: list[list[str]] = []

    def rowCount(self, parent=...): return len(self._data)

    def columnCount(self, parent=...): return len(self._headers)

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        return None

    def set_data(self, data: list[list[str]]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()


class JobManagerPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("任务管理", styleSheet="font-size: 24px; font-weight: bold;"))

        # Queue section
        layout.addWidget(QLabel("打印队列"))
        self.queue_empty_label = QLabel("队列为空，提交打印任务后将在此显示")
        self.queue_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.queue_empty_label.setStyleSheet("color: #9CA3AF; font-size: 14px; padding: 20px;")
        layout.addWidget(self.queue_empty_label)
        self.queue_table = QTableView()
        self.queue_model = SimpleTableModel(["文件名", "状态", "进度", "操作"])
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setVisible(False)
        layout.addWidget(self.queue_table)

        # History section
        layout.addWidget(QLabel("历史记录"))
        filter_row = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "完成", "失败", "已取消"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件名...")
        self.clear_filter_btn = QPushButton("清除筛选")
        self.clear_filter_btn.setVisible(False)
        self.clear_filter_btn.clicked.connect(self._clear_filter)
        filter_row.addWidget(QLabel("状态:"))
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(self.search_input)
        filter_row.addWidget(self.clear_filter_btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.history_table = QTableView()
        self.history_model = SimpleTableModel(
            ["ID", "文件名", "类型", "状态", "提交时间", "完成时间", "操作"]
        )
        self.history_table.setModel(self.history_model)
        self.history_table.setSortingEnabled(True)
        layout.addWidget(self.history_table)

        # Pagination
        pagination_row = QHBoxLayout()
        self.prev_btn = QPushButton("← 上一页")
        self.page_label = QLabel("第 1 页")
        self.next_btn = QPushButton("下一页 →")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        pagination_row.addStretch()
        pagination_row.addWidget(self.prev_btn)
        pagination_row.addWidget(self.page_label)
        pagination_row.addWidget(self.next_btn)
        pagination_row.addStretch()
        layout.addLayout(pagination_row)

        # Batch ops
        batch_row = QHBoxLayout()
        batch_row.addWidget(QPushButton("批量取消"))
        batch_row.addWidget(QPushButton("批量重试"))
        batch_row.addStretch()
        layout.addLayout(batch_row)

        self._page = 0
        self._page_size = 20

    def _clear_filter(self):
        self.status_filter.setCurrentIndex(0)
        self.search_input.clear()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.page_label.setText(f"第 {self._page + 1} 页")

    def _next_page(self):
        self._page += 1
        self.page_label.setText(f"第 {self._page + 1} 页")