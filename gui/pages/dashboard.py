"""Dashboard page: stat cards, recent jobs table."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)


class SkeletonCard(QFrame):
    """Placeholder card with pulsing animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('statCard')
        self._pulse = 0
        self._forward = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse_step)
        self._timer.start(50)

    def _pulse_step(self):
        if self._forward:
            self._pulse += 1
            if self._pulse >= 10:
                self._forward = False
        else:
            self._pulse -= 1
            if self._pulse <= 0:
                self._forward = True
        alpha = 180 + self._pulse * 6  # 180-240 range
        self.setStyleSheet(f"""
            QFrame#statCard {{
                background-color: rgba(200, 195, 185, {alpha});
                border: 1px solid #E5DDD5;
                border-radius: 12px;
                min-height: 100px;
            }}
        """)

    def stop_pulse(self):
        self._timer.stop()
        self.setStyleSheet('')
        self.setObjectName('statCard')
        self.style().unpolish(self)
        self.style().polish(self)


class StatCard(QFrame):
    """KPI card: label, large serif value with inline change, trend footer."""

    VALUE_COLORS = {
        'accent': '#8B7355',
        'success': '#6B8F6B',
        'error': '#C53A3A',
        'default': '#1C1917',
        'active': '#4A7FA5',
    }
    CHANGE_COLORS = {
        'up': '#6B8F6B',
        'down': '#C53A3A',
        'default': '#8A8178',
    }

    def __init__(
        self,
        label: str,
        value: str,
        variant: str = 'default',
        change: str = '',
        change_variant: str = 'default',
        trend: str = '',
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName('statCard')
        self._val_color = self.VALUE_COLORS.get(variant, '#1C1917')
        lo = QVBoxLayout(self)
        lo.setContentsMargins(24, 24, 24, 22)
        lo.setSpacing(0)

        lbl = QLabel(label)
        lbl.setObjectName('statLabel')
        lo.addWidget(lbl)
        lo.addSpacing(6)

        # Value + change inline
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName('statValue')
        val_color = self.VALUE_COLORS.get(variant, '#1C1917')
        self.value_lbl.setStyleSheet(f'color: {val_color};')
        row.addWidget(self.value_lbl)

        if change:
            self.change_lbl = QLabel(change)
            self.change_lbl.setObjectName('statChange')
            chg_color = self.CHANGE_COLORS.get(change_variant, '#8A8178')
            self.change_lbl.setStyleSheet(f'color: {chg_color};')
            row.addWidget(self.change_lbl)

        lo.addLayout(row)

        # Trend footer (separator + text)
        if trend:
            lo.addSpacing(8)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet('background-color: #EFE9E2; max-height: 1px;')
            lo.addWidget(sep)
            lo.addSpacing(6)

            trend_lbl = QLabel(trend)
            trend_lbl.setStyleSheet('font-size: 10px; color: #B0A89F; font-weight: 500;')
            lo.addWidget(trend_lbl)

    def set_value(self, value: str):
        self.value_lbl.setText(value)
        self.value_lbl.setStyleSheet(f'color: {self._val_color};')


class RecentJobsModel(QAbstractTableModel):
    """Read-only table model for recent jobs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._headers = ['ID', '文件名', '状态', '时间']
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

    def set_data(self, data):
        self.beginResetModel()
        self._data = data
        self.endResetModel()


class DashboardPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._event_bus = getattr(main_window, '_event_bus', None)
        self._skeleton_cards: list[SkeletonCard] = []
        self._initial_loaded = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Error banner with retry
        self.error_banner = QWidget()
        self.error_banner.setVisible(False)
        eb_lo = QHBoxLayout(self.error_banner)
        eb_lo.setContentsMargins(28, 8, 32, 8)
        self.error_label = QLabel('')
        self.error_label.setStyleSheet('color: #C53A3A;')
        self.retry_btn = QPushButton('重试')
        self.retry_btn.setObjectName('ghost')
        self.retry_btn.setProperty('compact', True)
        self.retry_btn.clicked.connect(self._refresh)
        eb_lo.addWidget(self.error_label, 1)
        eb_lo.addWidget(self.retry_btn)
        main_layout.addWidget(self.error_banner)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName('dashboardScroll')

        container = QWidget()
        lo = QVBoxLayout(container)
        lo.setContentsMargins(28, 28, 32, 28)
        lo.setSpacing(0)

        # ===== Page Header =====
        header = QWidget()
        hdr_lo = QHBoxLayout(header)
        hdr_lo.setContentsMargins(0, 0, 0, 0)

        title_group = QWidget()
        tg_lo = QHBoxLayout(title_group)
        tg_lo.setContentsMargins(0, 0, 0, 0)
        tg_lo.setSpacing(12)
        self.page_title = QLabel('仪表盘')
        self.page_title.setObjectName('pageTitle')
        self.page_sub = QLabel('今日概览')
        self.page_sub.setObjectName('pageSub')
        tg_lo.addWidget(self.page_title)
        tg_lo.addWidget(self.page_sub)
        hdr_lo.addWidget(title_group)
        hdr_lo.addStretch()

        actions = QWidget()
        act_lo = QHBoxLayout(actions)
        act_lo.setContentsMargins(0, 0, 0, 0)
        act_lo.setSpacing(8)
        refresh_btn = QPushButton('刷新')
        refresh_btn.setObjectName('ghost')
        refresh_btn.clicked.connect(self._refresh)
        new_job_btn = QPushButton('+ 新打印任务')
        new_job_btn.setObjectName('primary')
        new_job_btn.clicked.connect(lambda: main_window.sidebar.setCurrentRow(1))
        act_lo.addWidget(refresh_btn)
        act_lo.addWidget(new_job_btn)
        hdr_lo.addWidget(actions)

        lo.addWidget(header)
        lo.addSpacing(28)

        # ===== KPI Grid (2 rows × 3 cols) =====
        self._stats: dict[str, StatCard] = {}
        self._stat_widget = QWidget()
        self._kpi_grid = QGridLayout()
        self._kpi_grid.setSpacing(18)
        self._stat_widget.setLayout(self._kpi_grid)
        stat_defs = [
            ('排队中', '0', 'accent', '', 'default', ''),
            ('打印中', '0', 'active', '', 'default', ''),
            ('今日完成', '0', 'success', '', 'default', ''),
            ('今日失败', '0', 'error', '', 'default', ''),
            ('成功率', '0%', 'success', '', 'default', ''),
            ('总计', '0', 'accent', '历史累计', 'default', ''),
        ]
        for i, (title, val, variant, change, cv, trend) in enumerate(stat_defs):
            card = StatCard(title, val, variant, change, cv, trend)
            self._stats[title] = card
            self._kpi_grid.addWidget(card, i // 3, i % 3)
        lo.addWidget(self._stat_widget)
        lo.addSpacing(24)

        # ===== Recent Jobs Section =====
        self.recent_section = QWidget()
        rs_lo = QVBoxLayout(self.recent_section)
        rs_lo.setContentsMargins(0, 0, 0, 0)
        rs_lo.setSpacing(0)

        recent_heading = QLabel('最近任务')
        recent_heading.setObjectName('sectionHeading')
        rs_lo.addWidget(recent_heading)
        rs_lo.addSpacing(14)

        self.recent_table = QTableView()
        self.recent_table.setObjectName('recentTable')
        self.recent_model = RecentJobsModel()
        self.recent_table.setModel(self.recent_model)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setMaximumHeight(200)
        header = self.recent_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rs_lo.addWidget(self.recent_table)
        lo.addWidget(self.recent_section)

        lo.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # ===== Empty State =====
        self.empty_state = QWidget()
        empty_lo = QVBoxLayout(self.empty_state)
        empty_lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_text = QLabel('尚无打印任务')
        empty_text.setStyleSheet('font-size: 16px; color: #8A8178;')
        go_btn = QPushButton('前往快速打印')
        go_btn.setObjectName('primary')
        go_btn.clicked.connect(lambda: main_window.sidebar.setCurrentRow(1))
        empty_lo.addWidget(empty_text, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(go_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.empty_state)
        self.empty_state.setVisible(False)

        # ===== Refresh Timer (delayed, stopped when page hidden) =====
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        # Show skeleton on init
        self._show_skeleton()

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start(3000)
        self._refresh()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _show_skeleton(self):
        for card in self._stats.values():
            card.setVisible(False)
        for sk in self._skeleton_cards:
            sk.stop_pulse()
            sk.setParent(None)
            sk.deleteLater()
        self._skeleton_cards.clear()
        for i in range(6):
            sk = SkeletonCard()
            self._skeleton_cards.append(sk)
            self._kpi_grid.addWidget(sk, i // 3, i % 3)

    def _hide_skeleton(self):
        for sk in self._skeleton_cards:
            sk.stop_pulse()
            sk.setParent(None)
            sk.deleteLater()
        self._skeleton_cards.clear()
        for card in self._stats.values():
            card.setVisible(True)

    def _refresh(self):
        repo = getattr(self._mw._app.state, 'job_repo', None)
        if repo is None:
            return
        stats = repo.get_stats()
        total = stats.get('total', 0)

        # First successful load: hide skeleton
        if not self._initial_loaded:
            self._initial_loaded = True
            self._hide_skeleton()

        self._stats['排队中'].set_value(str(stats.get('queued', 0)))
        self._stats['打印中'].set_value(str(stats.get('printing', 0)))
        self._stats['今日完成'].set_value(str(stats.get('today_completed', 0)))
        self._stats['今日失败'].set_value(str(stats.get('today_failed', 0)))
        self._stats['成功率'].set_value(f'{stats.get("success_rate", 0):.0f}%')
        self._stats['总计'].set_value(str(total))

        has_data = total > 0
        self.empty_state.setVisible(not has_data and self._initial_loaded)

        # Recent jobs
        recent = repo.get_jobs(limit=10)
        recent_rows = [
            [
                str(j.get('id', '')),
                str(j.get('filename', '')),
                str(j.get('status', '')),
                str(j.get('created_at', '') or ''),
            ]
            for j in recent
        ]
        self.recent_model.set_data(recent_rows)
        self.recent_section.setVisible(has_data)

    def show_error(self, msg: str):
        self.error_label.setText(f'⚠ {msg}')
        self.error_banner.setVisible(True)
        self.error_banner.raise_()

    def on_job_status(self, data: dict):
        self._refresh()

    def on_printer_status(self, data: dict):
        pass
