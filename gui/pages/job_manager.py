"""Job manager page: queue + history tables with filter."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QEvent, QSettings, Qt, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyledItemDelegate,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui.components.skeleton import SkeletonWidget


class SimpleTableModel(QAbstractTableModel):
    """Read-only table model for job data."""

    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        self._headers = headers
        self._data: list[list[str]] = []

    def rowCount(self, parent=...):
        return len(self._data)

    def columnCount(self, parent=...):
        return len(self._headers)

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


class HoverHighlightDelegate(QStyledItemDelegate):
    """Delegate that highlights row background on hover."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovered_row = -1

    def set_hovered_row(self, row: int):
        self._hovered_row = row

    def paint(self, painter, option, index):
        if index.row() == self._hovered_row:
            painter.save()
            painter.fillRect(option.rect, QColor(238, 242, 255))
            painter.restore()
        super().paint(painter, option, index)


class JobManagerPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName('dashboardScroll')

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 28, 32, 28)

        title_lbl = QLabel('任务管理')
        title_lbl.setObjectName('pageTitle')
        layout.addWidget(title_lbl)

        # In-progress card
        self.active_card = QFrame()
        self.active_card.setObjectName('statCard')
        self.active_card.setVisible(False)
        ac_lo = QHBoxLayout(self.active_card)
        ac_lo.setContentsMargins(16, 12, 16, 12)
        self.active_icon = QLabel('📄')
        self.active_name = QLabel('')
        self.active_name.setObjectName('printName')
        self.active_status = QLabel('')
        self.active_status.setStyleSheet('font-size: 12px; color: #8B7355; font-weight: 600;')
        self.active_progress = QProgressBar()
        self.active_progress.setRange(0, 100)
        self.active_progress.setFixedWidth(120)
        self.active_cancel = QPushButton('取消')
        self.active_cancel.setObjectName('ghostDanger')
        self.active_cancel.setProperty('compact', True)
        ac_lo.addWidget(self.active_icon)
        ac_lo.addWidget(self.active_name)
        ac_lo.addWidget(self.active_status)
        ac_lo.addWidget(self.active_progress)
        ac_lo.addWidget(self.active_cancel)
        layout.addWidget(self.active_card)

        # Queue section
        layout.addWidget(QLabel('打印队列'))
        self.queue_empty_label = QLabel('队列为空，提交打印任务后将在此显示')
        self.queue_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.queue_empty_label.setStyleSheet('color: #8A8178; font-size: 14px; padding: 20px;')
        layout.addWidget(self.queue_empty_label)
        self.queue_table = QTableView()
        self.queue_table.setAlternatingRowColors(True)
        self.queue_model = SimpleTableModel(['文件名', '状态', '进度', '操作'])
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setVisible(False)
        layout.addWidget(self.queue_table)

        # Error widget with retry
        self.job_error_widget = QWidget()
        self.job_error_widget.setVisible(False)
        je_lo = QHBoxLayout(self.job_error_widget)
        je_lo.setContentsMargins(0, 0, 0, 0)
        self.job_error_label = QLabel('')
        self.job_error_label.setStyleSheet('color: #C53A3A; font-size: 13px;')
        self.job_retry_btn = QPushButton('重试')
        self.job_retry_btn.setObjectName('ghost')
        self.job_retry_btn.setProperty('compact', True)
        self.job_retry_btn.clicked.connect(self._refresh)
        je_lo.addWidget(self.job_error_label, 1)
        je_lo.addWidget(self.job_retry_btn)
        layout.addWidget(self.job_error_widget)

        # History section
        layout.addWidget(QLabel('历史记录'))
        filter_row = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(['全部', '完成', '失败', '已取消'])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索文件名...')
        self.clear_filter_btn = QPushButton('清除筛选')
        self.clear_filter_btn.setObjectName('ghost')
        self.clear_filter_btn.setProperty('compact', True)
        self.clear_filter_btn.setVisible(False)
        self.clear_filter_btn.clicked.connect(self._clear_filter)
        filter_row.addWidget(QLabel('状态:'))
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(self.search_input)
        filter_row.addWidget(self.clear_filter_btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.history_table = QTableView()
        self.history_table.setAlternatingRowColors(True)
        self.history_model = SimpleTableModel(
            ['ID', '文件名', '类型', '状态', '提交时间', '完成时间', '操作']
        )
        self.history_table.setModel(self.history_model)
        self.history_table.setSortingEnabled(True)
        layout.addWidget(self.history_table)

        # Skeleton loading placeholder
        self.history_skeleton = QWidget()
        self.history_skeleton.setVisible(False)
        skel_lo = QVBoxLayout(self.history_skeleton)
        skel_lo.setContentsMargins(0, 0, 0, 0)
        skel_lo.setSpacing(8)
        for _ in range(5):
            skel_lo.addWidget(SkeletonWidget(600, 22))
        skel_lo.addStretch()
        layout.addWidget(self.history_skeleton)

        # Pagination
        pagination_row = QHBoxLayout()
        self.prev_btn = QPushButton('← 上一页')
        self.page_label = QLabel('第 1 页')
        self.next_btn = QPushButton('下一页 →')
        self.prev_btn.setObjectName('ghost')
        self.prev_btn.setProperty('compact', True)
        self.next_btn.setObjectName('ghost')
        self.next_btn.setProperty('compact', True)
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
        self.batch_cancel_btn = QPushButton('批量取消')
        self.batch_cancel_btn.setObjectName('ghostDanger')
        self.batch_retry_btn = QPushButton('批量重试')
        self.batch_retry_btn.setObjectName('primary')
        self.batch_cancel_btn.clicked.connect(self._batch_cancel)
        self.batch_retry_btn.clicked.connect(self._batch_retry)
        batch_row.addWidget(self.batch_cancel_btn)
        batch_row.addWidget(self.batch_retry_btn)
        batch_row.addStretch()
        layout.addLayout(batch_row)

        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        self._page = 0
        self._page_size = 20

        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        self.search_input.textChanged.connect(self._on_filter_changed)

        # Hover delegate
        self._queue_delegate = HoverHighlightDelegate(self)
        self.queue_table.setItemDelegate(self._queue_delegate)
        self.queue_table.entered.connect(
            lambda idx: self._on_entered(self._queue_delegate, self.queue_table, idx)
        )
        self.queue_table.setMouseTracking(True)

        self._history_delegate = HoverHighlightDelegate(self)
        self.history_table.setItemDelegate(self._history_delegate)
        self.history_table.entered.connect(
            lambda idx: self._on_entered(self._history_delegate, self.history_table, idx)
        )
        self.history_table.setMouseTracking(True)

        self.queue_table.viewport().installEventFilter(self)
        self.history_table.viewport().installEventFilter(self)

        self._restore_table_state()

    _STATUS_MAP = {
        '全部': None,
        '完成': 'completed',
        '失败': 'failed',
        '已取消': 'cancelled',
    }

    @property
    def _current_status_filter(self) -> str | None:
        return self._STATUS_MAP.get(self.status_filter.currentText())

    def _on_filter_changed(self, *_):
        self._page = 0
        self.page_label.setText(f'第 {self._page + 1} 页')
        has_filter = self._current_status_filter is not None or bool(
            self.search_input.text().strip()
        )
        self.clear_filter_btn.setVisible(has_filter)
        self._refresh()

    def _clear_filter(self):
        self.status_filter.setCurrentIndex(0)
        self.search_input.clear()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.page_label.setText(f'第 {self._page + 1} 页')
            self._refresh()

    def _next_page(self):
        self._page += 1
        self.page_label.setText(f'第 {self._page + 1} 页')
        self._refresh()

    def _job_queue(self):
        app = getattr(self._mw, '_app', None)
        if app is None:
            return None
        return getattr(app.state, 'job_queue', None)

    def _batch_cancel(self):
        jq = self._job_queue()
        if jq is None:
            QMessageBox.warning(self, '批量取消', '服务尚未就绪')
            return
        reply = QMessageBox.question(
            self,
            '批量取消',
            '确定要取消所有排队中的任务吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.batch_cancel_btn.setEnabled(False)
        try:
            count = jq.cancel_all_queued()
        except Exception as e:
            QMessageBox.critical(self, '批量取消', f'操作失败: {e}')
            return
        finally:
            self.batch_cancel_btn.setEnabled(True)
        QMessageBox.information(self, '批量取消', f'已取消 {count} 个排队任务')
        self._refresh()

    def _batch_retry(self):
        jq = self._job_queue()
        repo = self._job_repo()
        if jq is None or repo is None:
            QMessageBox.warning(self, '批量重试', '服务尚未就绪')
            return
        search = self.search_input.text().strip() or None
        failed = repo.get_jobs(
            status='failed',
            search=search,
            limit=self._page_size,
            offset=self._page * self._page_size,
        )
        if not failed:
            QMessageBox.information(self, '批量重试', '当前页面没有失败的任务')
            return
        reply = QMessageBox.question(
            self,
            '批量重试',
            f'将重试当前页面 {len(failed)} 个失败任务，是否继续？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.batch_retry_btn.setEnabled(False)
        ok, fail = 0, 0
        try:
            for j in failed:
                new_id, _ = jq.retry_job(str(j.get('id', '')))
                if new_id:
                    ok += 1
                else:
                    fail += 1
        finally:
            self.batch_retry_btn.setEnabled(True)
        QMessageBox.information(
            self,
            '批量重试',
            f'成功 {ok} 个，失败 {fail} 个',
        )
        self._refresh()

    def _job_repo(self):
        app = getattr(self._mw, '_app', None)
        if app is None:
            return None
        return getattr(app.state, 'job_repo', None)

    def _refresh(self):
        self.job_error_widget.setVisible(False)
        repo = self._job_repo()
        if repo is None:
            self.history_skeleton.setVisible(True)
            self.history_table.setVisible(False)
            self.queue_empty_label.setText('加载失败')
            self.job_error_label.setText('无法连接数据库，请检查服务器状态')
            self.job_error_widget.setVisible(True)
            return
        self.history_skeleton.setVisible(False)
        self.history_table.setVisible(True)

        queued = repo.get_jobs_by_status('queued')
        printing = repo.get_jobs_by_status('printing')
        active = list(printing) + list(queued)

        # Active card
        if printing:
            p = printing[0]
            self.active_name.setText(str(p.get('filename', '')))
            self.active_status.setText('正在打印')
            self.active_progress.setValue(50)
            self.active_card.setVisible(True)
        else:
            self.active_card.setVisible(False)

        queue_rows = [
            [
                str(j.get('filename', '')),
                str(j.get('status', '')),
                '-',
                '取消',
            ]
            for j in active
        ]
        self.queue_model.set_data(queue_rows)
        has_active = bool(queue_rows)
        self.queue_table.setVisible(has_active)
        self.queue_empty_label.setVisible(not has_active)

        search = self.search_input.text().strip() or None
        history = repo.get_jobs(
            status=self._current_status_filter,
            search=search,
            limit=self._page_size,
            offset=self._page * self._page_size,
        )
        history_rows = [
            [
                str(j.get('id', '')),
                str(j.get('filename', '')),
                str(j.get('file_type', '')),
                str(j.get('status', '')),
                str(j.get('created_at', '') or ''),
                str(j.get('completed_at', '') or ''),
                '重试',
            ]
            for j in history
        ]
        self.history_model.set_data(history_rows)

        if hasattr(self._mw, '_state_manager'):
            self._mw._state_manager.restore_table_state('history', self.history_table)

    def on_job_status(self, data: dict):
        self._refresh()

    def on_log(self, data: dict):
        # Stub
        pass

    def _on_entered(self, delegate, table, index):
        old = delegate._hovered_row
        delegate.set_hovered_row(index.row())
        if old >= 0:
            table.update(table.visualRect(table.model().index(old, 0)))
        table.update(table.visualRect(index))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Leave and obj in (
            self.queue_table.viewport(),
            self.history_table.viewport(),
        ):
            delegate = (
                self._queue_delegate
                if obj is self.queue_table.viewport()
                else self._history_delegate
            )
            old = delegate._hovered_row
            delegate.set_hovered_row(-1)
            table = self.queue_table if obj is self.queue_table.viewport() else self.history_table
            if old >= 0:
                table.update(table.visualRect(table.model().index(old, 0)))
            return False
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self._save_table_state()
        super().hideEvent(event)

    def _save_table_state(self):
        settings = QSettings('iOSPrintServer', 'job_manager')
        settings.beginGroup('history_table')
        for col in range(self.history_model.columnCount()):
            settings.setValue(f'col_{col}_width', self.history_table.columnWidth(col))
        if self.history_table.horizontalHeader().sortIndicatorSection() >= 0:
            settings.setValue(
                'sort_column', self.history_table.horizontalHeader().sortIndicatorSection()
            )
            order = self.history_table.horizontalHeader().sortIndicatorOrder()
            settings.setValue('sort_order', order.value)
        settings.endGroup()

    def _restore_table_state(self):
        settings = QSettings('iOSPrintServer', 'job_manager')
        settings.beginGroup('history_table')
        for col in range(self.history_model.columnCount()):
            w = settings.value(f'col_{col}_width', type=int)
            if w:
                self.history_table.setColumnWidth(col, w)
        sort_col = settings.value('sort_column', type=int)
        sort_order = settings.value('sort_order')
        if sort_col is not None:
            order = (
                Qt.SortOrder(int(sort_order))
                if sort_order is not None
                else Qt.SortOrder.AscendingOrder
            )
            self.history_table.sortByColumn(sort_col, order)
        settings.endGroup()

    def _highlight_row(self, row: int):
        """Fade row background briefly on status change."""
        anim = QVariantAnimation(self)
        anim.setDuration(800)
        anim.setStartValue(QColor('#E8DFD4'))
        anim.setEndValue(QColor(0, 0, 0, 0))
        idx = self.history_model.index(row, 0)
        anim.valueChanged.connect(
            lambda v: self.history_table.model().setData(idx, v, Qt.ItemDataRole.BackgroundRole)
        )
        anim.start()
