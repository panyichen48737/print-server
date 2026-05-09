"""Dashboard page: stat cards, grouped bar chart."""
from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)


class StatCard(QFrame):
    """KPI card: label, large serif value with inline change, trend footer."""
    VALUE_COLORS = {
        "accent": "#8B7355", "success": "#6B8F6B",
        "error": "#C53A3A", "default": "#1C1917", "active": "#4A7FA5",
    }
    CHANGE_COLORS = {
        "up": "#6B8F6B", "down": "#C53A3A", "default": "#8A8178",
    }

    def __init__(self, label: str, value: str, variant: str = "default",
                 change: str = "", change_variant: str = "default",
                 trend: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")
        self._val_color = self.VALUE_COLORS.get(variant, "#1C1917")
        lo = QVBoxLayout(self)
        lo.setContentsMargins(24, 24, 24, 22)
        lo.setSpacing(0)

        lbl = QLabel(label)
        lbl.setObjectName("statLabel")
        lo.addWidget(lbl)
        lo.addSpacing(6)

        # Value + change inline
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("statValue")
        val_color = self.VALUE_COLORS.get(variant, "#1C1917")
        self.value_lbl.setStyleSheet(f"color: {val_color};")
        row.addWidget(self.value_lbl)

        if change:
            self.change_lbl = QLabel(change)
            self.change_lbl.setObjectName("statChange")
            chg_color = self.CHANGE_COLORS.get(change_variant, "#8A8178")
            self.change_lbl.setStyleSheet(f"color: {chg_color};")
            row.addWidget(self.change_lbl)

        lo.addLayout(row)

        # Trend footer (separator + text)
        if trend:
            lo.addSpacing(8)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("background-color: #EFE9E2; max-height: 1px;")
            lo.addWidget(sep)
            lo.addSpacing(6)

            trend_lbl = QLabel(trend)
            trend_lbl.setStyleSheet("font-size: 10px; color: #B0A89F; font-weight: 500;")
            lo.addWidget(trend_lbl)

    def set_value(self, value: str):
        self.value_lbl.setText(value)
        self.value_lbl.setStyleSheet(f"color: {self._val_color};")


class BarChartWidget(QWidget):
    """Custom painted grouped bar chart."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple[str, int, int]] = []
        self._max_value = 0
        self.setMinimumHeight(120)

    def set_data(self, data: list[tuple[str, int, int]]):
        self._data = data
        self._max_value = max((max(v1, v2) for _, v1, v2 in data), default=0)
        self.update()

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        bar_c1 = QColor("#8B7355")
        bar_c1.setAlpha(191)
        bar_c2 = QColor("#6B8F6B")
        bar_c2.setAlpha(191)

        n = len(self._data)
        pad = 20
        label_h = 24
        chart_h = h - label_h - 8
        total_w = w - pad * 2
        group_w = min(60, max(20, int(total_w / max(n, 1))))
        gap = 3
        bar_w = min(12, group_w // 2 - gap)
        spacing = max(8, (total_w - n * group_w) // max(n - 1, 1)) if n > 1 else 0

        for i, (label, v1, v2) in enumerate(self._data):
            cx = pad + i * (group_w + spacing) + group_w / 2
            max_h = chart_h
            h1 = int((v1 / self._max_value) * max_h) if self._max_value > 0 else 0
            h2 = int((v2 / self._max_value) * max_h) if self._max_value > 0 else 0

            if h1 > 0:
                p.setBrush(bar_c1)
                p.setPen(Qt.PenStyle.NoPen)
                x1 = int(cx - bar_w - gap / 2)
                p.drawRoundedRect(x1, h - label_h - h1, bar_w, h1, 3, 3)
            if h2 > 0:
                p.setBrush(bar_c2)
                p.setPen(Qt.PenStyle.NoPen)
                x2 = int(cx + gap / 2)
                p.drawRoundedRect(x2, h - label_h - h2, bar_w, h2, 3, 3)

            p.setPen(QColor("#B0A89F"))
            font = p.font()
            font.setPixelSize(10)
            p.setFont(font)
            p.drawText(QRectF(cx - group_w / 2, h - label_h + 4, group_w, label_h),
                       Qt.AlignmentFlag.AlignCenter, label)


class DashboardPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._event_bus = getattr(main_window, "_event_bus", None)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Error banner
        self.error_banner = QLabel("")
        self.error_banner.setVisible(False)
        self.error_banner.setStyleSheet(
            "background-color: #FBF0F0; color: #C53A3A; padding: 8px 16px;"
        )
        main_layout.addWidget(self.error_banner)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("dashboardScroll")

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
        self.page_title = QLabel("仪表盘")
        self.page_title.setObjectName("pageTitle")
        self.page_sub = QLabel("今日概览")
        self.page_sub.setObjectName("pageSub")
        tg_lo.addWidget(self.page_title)
        tg_lo.addWidget(self.page_sub)
        hdr_lo.addWidget(title_group)
        hdr_lo.addStretch()

        actions = QWidget()
        act_lo = QHBoxLayout(actions)
        act_lo.setContentsMargins(0, 0, 0, 0)
        act_lo.setSpacing(8)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("ghost")
        refresh_btn.clicked.connect(self._refresh)
        new_job_btn = QPushButton("+ 新打印任务")
        new_job_btn.setObjectName("primary")
        new_job_btn.clicked.connect(lambda: main_window.sidebar.setCurrentRow(1))
        act_lo.addWidget(refresh_btn)
        act_lo.addWidget(new_job_btn)
        hdr_lo.addWidget(actions)

        lo.addWidget(header)
        lo.addSpacing(28)

        # ===== KPI Grid (2 rows × 3 cols) =====
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(18)
        self._stats: dict[str, StatCard] = {}
        stat_defs = [
            ("排队中", "0", "accent", "", "default", ""),
            ("打印中", "0", "active", "", "default", ""),
            ("今日完成", "0", "success", "", "default", ""),
            ("今日失败", "0", "error", "", "default", ""),
            ("成功率", "0%", "success", "", "default", ""),
            ("总计", "0", "accent", "历史累计", "default", ""),
        ]
        for i, (title, val, variant, change, cv, trend) in enumerate(stat_defs):
            card = StatCard(title, val, variant, change, cv, trend)
            self._stats[title] = card
            kpi_grid.addWidget(card, i // 3, i % 3)
        lo.addLayout(kpi_grid)
        lo.addSpacing(24)

        # ===== Chart Section =====
        self.chart_section = QWidget()
        cs_lo = QVBoxLayout(self.chart_section)
        cs_lo.setContentsMargins(0, 0, 0, 0)
        cs_lo.setSpacing(0)

        chart_heading = QLabel("近 7 天打印趋势")
        chart_heading.setObjectName("sectionHeading")
        cs_lo.addWidget(chart_heading)
        cs_lo.addSpacing(14)

        chart_area = QFrame()
        chart_area.setObjectName("chartArea")
        ca_lo = QVBoxLayout(chart_area)
        ca_lo.setContentsMargins(22, 24, 22, 24)
        ca_lo.setSpacing(0)

        chart_header = QWidget()
        ch_lo = QHBoxLayout(chart_header)
        ch_lo.setContentsMargins(0, 0, 0, 0)
        chart_label = QLabel("任务数 / 页数")
        chart_label.setObjectName("chartLabel")
        ch_lo.addWidget(chart_label)
        ch_lo.addStretch()

        legend = QWidget()
        leg_lo = QHBoxLayout(legend)
        leg_lo.setContentsMargins(0, 0, 0, 0)
        leg_lo.setSpacing(14)
        for color, text in [("#8B7355", "任务数"), ("#6B8F6B", "打印页数")]:
            item = QWidget()
            il = QHBoxLayout(item)
            il.setContentsMargins(0, 0, 0, 0)
            il.setSpacing(5)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            label = QLabel(text)
            label.setStyleSheet("font-size: 11px; color: #8A8178;")
            il.addWidget(dot)
            il.addWidget(label)
            leg_lo.addWidget(item)
        ch_lo.addWidget(legend)
        ca_lo.addWidget(chart_header)
        ca_lo.addSpacing(16)

        self.bar_chart = BarChartWidget()
        ca_lo.addWidget(self.bar_chart, 1)
        cs_lo.addWidget(chart_area)
        cs_lo.addSpacing(28)
        lo.addWidget(self.chart_section)

        lo.addStretch()
        scroll.setWidget(container)
        main_layout.addWidget(scroll, 1)

        # ===== Empty State =====
        self.empty_state = QWidget()
        empty_lo = QVBoxLayout(self.empty_state)
        empty_lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_text = QLabel("尚无打印任务")
        empty_text.setStyleSheet("font-size: 16px; color: #8A8178;")
        go_btn = QPushButton("前往快速打印")
        go_btn.setObjectName("primary")
        go_btn.clicked.connect(lambda: main_window.sidebar.setCurrentRow(1))
        empty_lo.addWidget(empty_text, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(go_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.empty_state)
        self.empty_state.setVisible(False)

        # ===== Refresh Timer =====
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)

    def _refresh(self):
        repo = getattr(self._mw._app.state, "job_repo", None)
        if repo is None:
            return
        stats = repo.get_stats()
        total = stats.get("total", 0)
        self._stats["排队中"].set_value(str(stats.get("queued", 0)))
        self._stats["打印中"].set_value(str(stats.get("printing", 0)))
        self._stats["今日完成"].set_value(str(stats.get("today_completed", 0)))
        self._stats["今日失败"].set_value(str(stats.get("today_failed", 0)))
        self._stats["成功率"].set_value(f"{stats.get('success_rate', 0):.0f}%")
        self._stats["总计"].set_value(str(total))

        has_data = total > 0
        self.empty_state.setVisible(not has_data)
        self.chart_section.setVisible(has_data)

        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        today = datetime.date.today()
        daily = repo.get_daily_counts(7)
        data = []
        for i in range(6, -1, -1):
            d = today - datetime.timedelta(days=i)
            ds = d.strftime("%Y-%m-%d")
            count = daily.get(ds, 0)
            label = weekday_names[d.weekday()]
            data.append((label, count, 0))
        self.bar_chart.set_data(data)

    def show_loading(self):
        self.error_banner.setVisible(False)
        self.empty_state.setVisible(False)
        for card in self._stats.values():
            card.set_value("---")
            card.value_lbl.setStyleSheet("color: #D0C8BE;")

    def show_error(self, msg: str):
        self.error_banner.setText(f"⚠ {msg}")
        self.error_banner.setVisible(True)

    def on_job_status(self, data: dict):
        self._refresh()

    def on_printer_status(self, data: dict):
        pass