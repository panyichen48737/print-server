"""Job manager page: active queue + history table with filter/pagination/bulk ops."""
import flet as ft

from gui.components.job_table import status_badge
from gui.http_client import get_client


class JobManagerPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.status_filter = ft.Dropdown(
            label="状态", width=150,
            options=[
                ft.dropdown.Option("all", "全部"),
                ft.dropdown.Option("pending", "排队中"),
                ft.dropdown.Option("printing", "打印中"),
                ft.dropdown.Option("completed", "已完成"),
                ft.dropdown.Option("failed", "失败"),
                ft.dropdown.Option("cancelled", "已取消"),
            ],
            value="all",
        )
        self.search_input = ft.TextField(label="搜索文件名", width=250)
        self.table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("文件名")),
                ft.DataColumn(ft.Text("类型")),
                ft.DataColumn(ft.Text("大小")),
                ft.DataColumn(ft.Text("状态")),
                ft.DataColumn(ft.Text("提交时间")),
                ft.DataColumn(ft.Text("操作")),
            ],
        )
        self.pagination = ft.Row([
            ft.TextButton("上一页"),
            ft.Text("第 1 页"),
            ft.TextButton("下一页"),
        ])
        self.queue_section = ft.Column()

        self.content = ft.Column([
            ft.Text("任务管理", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("打印队列", weight=ft.FontWeight.BOLD, size=18),
            self.queue_section,
            ft.Divider(),
            ft.Row([
                self.status_filter,
                self.search_input,
                ft.FilledButton("搜索", on_click=self._search),
                ft.FilledTonalButton("批量取消"),
                ft.FilledTonalButton("批量重试"),
            ]),
            self.table,
            self.pagination,
        ])
        self._load(0)

    async def _load(self, offset: int):
        try:
            client = get_client()
            status = self.status_filter.value if self.status_filter.value != "all" else None
            params: dict = {"limit": 20, "offset": offset}
            if status:
                params["status"] = status
            if self.search_input.value:
                params["search"] = self.search_input.value
            resp = await client.get("/admin/api/jobs", params=params)
            jobs = resp.json()
            self.table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(j.get("id", "")))),
                    ft.DataCell(ft.Text(j.get("filename", ""), max_lines=1)),
                    ft.DataCell(ft.Text(j.get("file_type", ""))),
                    ft.DataCell(ft.Text(j.get("file_size", ""))),
                    ft.DataCell(status_badge(j.get("status", ""))),
                    ft.DataCell(ft.Text(j.get("created_at", ""))),
                    ft.DataCell(ft.Row([
                        ft.IconButton(
                            ft.icons.CANCEL, tooltip="取消", icon_size=18,
                            on_click=lambda _, jid=j["id"]: self._cancel(jid),
                        ),
                        ft.IconButton(
                            ft.icons.REPLAY, tooltip="重试", icon_size=18,
                            on_click=lambda _, jid=j["id"]: self._retry(jid),
                        ),
                    ])),
                ]) for j in jobs
            ]
            self.update()
        except Exception as e:
            from gui.components.notification import show_snackbar
            show_snackbar(self.page, f"加载失败: {e}", color=ft.Colors.RED)

    async def _cancel(self, job_id: int):
        client = get_client()
        await client.post(f"/api/cancel/{job_id}")
        self._load(0)

    async def _retry(self, job_id: int):
        client = get_client()
        await client.post(f"/api/retry/{job_id}")
        self._load(0)

    def _search(self, e):
        self._load(0)
