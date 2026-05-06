"""Printer management page: card grid with status, set default."""
import flet as ft

from gui.components.notification import show_snackbar
from gui.components.printer_card import PrinterCard
from gui.http_client import get_client


class PrinterManagerPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.card_grid = ft.Row(wrap=True, spacing=16)
        self.content = ft.Column([
            ft.Row([
                ft.Text("打印机管理", size=24, weight=ft.FontWeight.BOLD),
                ft.FilledButton("刷新状态", icon=ft.icons.REFRESH, on_click=self._refresh),
            ]),
            self.card_grid,
            ft.Text("打印机状态每 30 秒自动更新", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ])
        self._load()

    async def _load(self):
        try:
            client = get_client()
            resp = await client.get("/api/printers/status")
            printers = resp.json()
            default_resp = await client.get("/api/config")
            default_printer = default_resp.json().get("default_printer", "")
            self.card_grid.controls = [
                PrinterCard(
                    name=p.get("name", ""),
                    overall=p.get("overall", ""),
                    statuses=p.get("statuses", []),
                    is_default=p.get("name") == default_printer,
                    on_set_default=self._set_default,
                ) for p in printers
            ]
            self.update()
        except Exception as e:
            show_snackbar(self.page, f"加载失败: {e}", color=ft.Colors.RED)

    async def _set_default(self, name: str):
        try:
            client = get_client()
            await client.post("/api/set_default_printer", json={"printer": name})
            show_snackbar(self.page, f"已设 {name} 为默认打印机")
            await self._load()
        except Exception as e:
            show_snackbar(self.page, f"设置失败: {e}", color=ft.Colors.RED)

    def _refresh(self, e):
        self._load()
