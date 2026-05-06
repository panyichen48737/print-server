"""Quick print page: file picker, print options, submit."""

import flet as ft

from gui.http_client import get_client


class QuickPrintPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self._file_path: str | None = None
        self.selected_file = ft.Text("未选择文件", color=ft.Colors.ON_SURFACE_VARIANT)
        self.printer_dropdown = ft.Dropdown(label="打印机", width=300)
        self.copies_input = ft.TextField(
            label="份数", value="1", width=100, keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.duplex_switch = ft.Switch(label="双面", value=True)
        self.color_switch = ft.Switch(label="颜色", value=True)
        self.paper_size = ft.Dropdown(
            label="纸张大小", width=150,
            options=[
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("Letter"),
                ft.dropdown.Option("A3"),
            ],
            value="A4",
        )
        self.progress = ft.ProgressBar(visible=False)

        # File picker (must be added to page.overlay before use)
        self.file_picker = ft.FilePicker()
        page.overlay.append(self.file_picker)

        self.content = ft.Column([
            ft.Text("快速打印", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.icons.CLOUD_UPLOAD, size=48, color=ft.Colors.PRIMARY),
                    ft.Text("拖拽文件到此处或点击选择", size=16),
                    self.selected_file,
                ], alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                height=200,
                border=ft.border.all(2, ft.Colors.PRIMARY, style=ft.BorderStyle.DASHED),
                border_radius=12,
                ink=True,
                on_click=self._pick_file,
            ),
            ft.Row([self.printer_dropdown, self.copies_input], spacing=16),
            ft.Row([self.duplex_switch, self.color_switch, self.paper_size], spacing=16),
            self.progress,
            ft.FilledButton("开始打印", icon=ft.icons.PRINT, on_click=self._submit_print),
        ], spacing=16)
        self._load_printers()

    async def _load_printers(self):
        try:
            client = get_client()
            resp = await client.get("/api/printers")
            printers = resp.json()
            self.printer_dropdown.options = [ft.dropdown.Option(p) for p in printers]
            self.update()
        except Exception:
            pass

    async def _pick_file(self, e):
        files = await self.file_picker.pick_files(
            dialog_title="选择打印文件",
            allow_multiple=False,
        )
        if files:
            f = files[0]
            self.selected_file.value = f"{f.name} ({f.size / 1024:.1f} KB)"
            self._file_path = f.path
            self.selected_file.update()

    async def _submit_print(self, e):
        if not self._file_path:
            from gui.components.notification import show_snackbar
            show_snackbar(self.page, "请先选择文件", color=ft.Colors.AMBER)
            return
        self.progress.visible = True
        self.progress.update()
        try:
            client = get_client()
            with open(self._file_path, "rb") as f:
                files = {"file": f}
                data = {
                    "printer": self.printer_dropdown.value or "",
                    "copies": self.copies_input.value or "1",
                    "duplex": str(self.duplex_switch.value).lower(),
                    "color": str(self.color_switch.value).lower(),
                    "paper_size": self.paper_size.value or "A4",
                }
                resp = await client.post("/api/print", data=data, files=files)
            from gui.components.notification import show_snackbar
            if resp.status_code == 200:
                show_snackbar(self.page, "打印任务已提交")
            else:
                show_snackbar(self.page, f"提交失败: {resp.text}", color=ft.Colors.RED)
        except Exception as ex:
            from gui.components.notification import show_snackbar
            show_snackbar(self.page, f"错误: {ex}", color=ft.Colors.RED)
        finally:
            self.progress.visible = False
            self.progress.update()
