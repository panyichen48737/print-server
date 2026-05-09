"""Dashboard page: stat cards, chart, printer cards, recent jobs."""
from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
from PySide6.QtCore import Qt, QTimer, QDateTime
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QPushButton


class StatCard(QFrame):
    def __init__(self, title: str, value: str, color: str = "#1F2937", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)


class DashboardPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._event_bus = getattr(main_window, "_event_bus", None)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title
        title = QLabel("仪表盘")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Status row
        self.status_row = QHBoxLayout()
        layout.addLayout(self.status_row)

        # 6 stat cards in grid (2x3)
        self.stat_grid = QGridLayout()
        self.stat_grid.setSpacing(12)
        self._stats: dict[str, StatCard] = {}
        stat_defs = [
            ("排队中", "0", "#4F46E5"), ("打印中", "0", "#F59E0B"),
            ("今日完成", "0", "#16A34A"), ("今日失败", "0", "#DC2626"),
            ("成功率", "0%", "#16A34A"), ("总计", "0", "#1F2937"),
        ]
        for i, (title, val, color) in enumerate(stat_defs):
            card = StatCard(title, val, color)
            self._stats[title] = card
            self.stat_grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(self.stat_grid)

        # Error banner (hidden by default)
        self.error_banner = QLabel("")
        self.error_banner.setVisible(False)
        self.error_banner.setStyleSheet(
            "background-color: #FEE2E2; color: #DC2626; padding: 8px 16px; border-radius: 4px;"
        )
        layout.addWidget(self.error_banner)

        # Empty state (first-run)
        self.empty_state = QWidget()
        empty_lo = QVBoxLayout(self.empty_state)
        empty_lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("📊")
        empty_icon.setStyleSheet("font-size: 48px;")
        empty_text = QLabel("尚无打印任务")
        empty_text.setStyleSheet("font-size: 16px; color: #6B7280;")
        go_print_btn = QPushButton("前往快速打印")
        go_print_btn.clicked.connect(lambda: main_window.nav.setCurrentRow(1))
        empty_lo.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(empty_text, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(go_print_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_state)
        self.empty_state.setVisible(False)

        # QChart - 7-day print trend
        self._chart = QChart()
        self._chart.setTitle("近 7 天打印趋势")
        self._chart.legend().hide()
        self._series = QLineSeries()
        self._chart.addSeries(self._series)
        self._axis_x = QDateTimeAxis()
        self._axis_x.setFormat("MM-dd")
        self._axis_x.setLabelsAngle(-45)
        self._chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)
        self._series.attachAxis(self._axis_x)
        self._axis_y = QValueAxis()
        self._axis_y.setLabelFormat("%d")
        self._axis_y.setMin(0)
        self._chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)
        self._series.attachAxis(self._axis_y)

        self.chart_view = QChartView(self._chart)
        self.chart_view.setFixedHeight(200)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(self.chart_view)

        # Printer cards + Recent jobs row
        bottom_row = QHBoxLayout()
        self.printer_area = QVBoxLayout()
        self.printer_area.addWidget(QLabel("打印机状态"))
        bottom_row.addLayout(self.printer_area)
        self.jobs_area = QVBoxLayout()
        self.jobs_area.addWidget(QLabel("最近任务"))
        bottom_row.addLayout(self.jobs_area)
        layout.addLayout(bottom_row)

        # Refresh timer (stub - connected via EventBus in Task 13)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)

    def _refresh(self):
        repo = self._mw._app.state.job_repo
        stats = repo.get_stats()
        total = stats.get("total", 0)
        self._stats["排队中"].value_label.setText(str(stats.get("queued", 0)))
        self._stats["打印中"].value_label.setText(str(stats.get("printing", 0)))
        self._stats["今日完成"].value_label.setText(str(stats.get("today_completed", 0)))
        self._stats["今日失败"].value_label.setText(str(stats.get("today_failed", 0)))
        self._stats["成功率"].value_label.setText(f"{stats.get('success_rate', 0):.0f}%")
        self._stats["总计"].value_label.setText(str(total))

        if total == 0:
            self.empty_state.setVisible(True)
            self.chart_view.setVisible(False)
            return

        self.empty_state.setVisible(False)
        self.chart_view.setVisible(True)

        daily = repo.get_daily_counts(7)
        self._series.clear()
        max_y = 0
        sorted_days = sorted(daily.items())
        min_ts = max_ts = None
        for date_str, count in sorted_days:
            dt = QDateTime.fromString(date_str, "yyyy-MM-dd")
            secs = dt.toSecsSinceEpoch()
            self._series.append(QDateTime.fromSecsSinceEpoch(secs).toMSecsSinceEpoch(), count)
            max_y = max(max_y, count)
            if min_ts is None or secs < min_ts:
                min_ts = secs
            if max_ts is None or secs > max_ts:
                max_ts = secs
        if min_ts is not None and max_ts is not None:
            self._axis_x.setRange(QDateTime.fromSecsSinceEpoch(min_ts), QDateTime.fromSecsSinceEpoch(max_ts))
        self._axis_y.setMax(max(max_y, 1))

    def show_loading(self):
        self.error_banner.setVisible(False)
        self.empty_state.setVisible(False)
        for card in self._stats.values():
            card.value_label.setText("---")
            card.value_label.setStyleSheet("color: #D1D5DB; font-size: 24px; font-weight: bold;")

    def show_error(self, msg: str):
        self.error_banner.setText(f"⚠ {msg}")
        self.error_banner.setVisible(True)

    def on_job_status(self, data: dict):
        self._refresh()

    def on_printer_status(self, data: dict):
        # Add/replace printer cards
        pass