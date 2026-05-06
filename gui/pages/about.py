"""About page: version info, update check, links."""
import flet as ft
import httpx

from gui.http_client import get_client


class AboutPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.update_status = ft.Text("")

        import gui
        version = gui.__version__

        self.content = ft.Column([
            ft.Icon(ft.icons.PRINT, size=64, color=ft.Colors.PRIMARY),
            ft.Text("iOS 云打印服务器", size=28, weight=ft.FontWeight.BOLD),
            ft.Text(f"版本: {version}", size=16),
            ft.Text(f"Python: {__import__('sys').version.split()[0]}", size=14),
            ft.Row([
                ft.FilledButton("检查更新", icon=ft.icons.UPDATE, on_click=self._check_update),
                ft.OutlinedButton("日志文件夹"),
                ft.OutlinedButton("配置文件"),
            ]),
            self.update_status,
            ft.Divider(),
            ft.Text(
                "iOS 云打印服务器 — Windows 打印服务器",
                size=12, color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            ft.Text(
                "接收 iOS Scriptable 和 Web 请求，通过 pywin32 驱动本地打印机",
                size=12, color=ft.Colors.ON_SURFACE_VARIANT,
            ),
        ], alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True)

    async def _check_update(self, e):
        self.update_status.value = "正在检查更新..."
        self.update_status.color = ft.Colors.ON_SURFACE_VARIANT
        self.update_status.update()
        try:
            client = get_client()
            resp = await client.get("/api/version")
            version = resp.json().get("version", "0.0.0")
            gh_resp = await httpx.AsyncClient().get(
                "https://api.github.com/repos/panyichen48737/print-server/releases/latest",
                timeout=5.0,
            )
            gh_data = gh_resp.json()
            latest = gh_data.get("tag_name", "").lstrip("v")
            if latest > version:
                self.update_status.value = f"新版本 v{latest} 可用！"
                self.update_status.color = ft.Colors.GREEN
            else:
                self.update_status.value = f"已是最新版本 (v{version})"
                self.update_status.color = ft.Colors.GREEN
        except Exception as ex:
            self.update_status.value = f"检查更新失败: {ex}"
            self.update_status.color = ft.Colors.RED
        self.update_status.update()
