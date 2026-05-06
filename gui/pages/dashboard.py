"""Dashboard page: server status, 6 stat cards, recent jobs, printer status."""
import flet as ft

from gui.components.job_table import build_job_rows
from gui.components.skeleton import card_skeleton
from gui.components.status_card import StatusCard
from gui.http_client import get_client


class DashboardPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.stats_row = ft.Row(wrap=True, spacing=16)
        self.recent_jobs = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("文件名")),
                ft.DataColumn(ft.Text("状态")),
                ft.DataColumn(ft.Text("时间")),
            ],
        )
        self.printer_status = ft.Column()
        self.status_bar = ft.Container(bgcolor=ft.Colors.GREY_200, padding=10)

        self.content = ft.Column([
            self.status_bar,
            ft.Text("仪表盘", size=24, weight=ft.FontWeight.BOLD),
            self.stats_row,
            ft.Row([
                ft.Column([ft.Text("打印机状态", weight=ft.FontWeight.BOLD), self.printer_status], expand=1),
                ft.Column([ft.Text("最近任务", weight=ft.FontWeight.BOLD), self.recent_jobs], expand=2),
            ], expand=True),
        ])
        self._load_data()

    def _load_data(self):
        self.stats_row.controls = [card_skeleton() for _ in range(6)]
        self.update()
        self.page.run_task(self._fetch_data)

    async def _fetch_data(self):
        try:
            client = get_client()
            health = await client.get("/api/health")
            health_data = health.json()
            self.status_bar.content = ft.Row([
                ft.Container(width=10, height=10, bgcolor=ft.Colors.GREEN, border_radius=5),
                ft.Text(
                    f"运行中 · 端口 {health_data.get('port', 5000)}"
                    f" · 队列: {health_data.get('queue_size', 0)}"
                ),
            ])

            stats = await client.get("/admin/api/stats")
            stats_data = stats.json()
            icons = [
                ft.icons.HOURGLASS_EMPTY, ft.icons.PRINT, ft.icons.CHECK_CIRCLE,
                ft.icons.ERROR, ft.icons.TRENDING_UP, ft.icons.ANALYTICS,
            ]
            labels = ["排队中", "打印中", "今日完成", "今日失败", "成功率", "总计"]
            self.stats_row.controls = [
                StatusCard(label, str(stats_data.get(label, 0)), icon)
                for label, icon in zip(labels, icons)
            ]

            jobs = await client.get("/admin/api/jobs", params={"limit": 10})
            self.recent_jobs.rows = build_job_rows(jobs.json())
        except Exception as e:
            self.status_bar.bgcolor = ft.Colors.RED_100
            self.status_bar.content = ft.Text(f"连接失败: {e}")
        self.update()
