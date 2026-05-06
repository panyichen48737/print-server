"""Real-time log viewer with filter, pause, auto-scroll."""
import flet as ft

from gui.components.log_list import build_log_row
from gui.http_client import get_client
from gui.sse_client import sse


class LogsPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self._paused = False
        self._paused_count = 0
        self._log_lines: list[ft.Row] = []

        self.level_filter = ft.Dropdown(
            label="级别", width=150,
            options=[
                ft.dropdown.Option("ALL", "全部"),
                ft.dropdown.Option("ERROR"),
                ft.dropdown.Option("WARNING"),
                ft.dropdown.Option("INFO"),
                ft.dropdown.Option("DEBUG"),
            ],
            value="ALL",
        )
        self.search_filter = ft.TextField(label="搜索", width=250)
        self.pause_btn = ft.IconButton(ft.icons.PAUSE, tooltip="暂停", on_click=self._toggle_pause)
        self.clear_btn = ft.IconButton(ft.icons.CLEAR_ALL, tooltip="清空", on_click=self._clear)
        self.auto_scroll_switch = ft.Switch(label="自动滚动", value=True)
        self.pause_banner = ft.Container(
            visible=False, bgcolor=ft.Colors.BLUE_100,
            padding=8, content=ft.Text(""),
        )
        self.log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)

        self.content = ft.Column([
            ft.Text("实时日志", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([
                self.level_filter, self.search_filter, self.pause_btn, self.clear_btn,
                self.auto_scroll_switch, ft.TextButton("打开日志文件夹"),
            ]),
            self.pause_banner,
            self.log_list,
            ft.FilledTonalButton("复制全部日志"),
        ], expand=True)

        sse.on("log", self._on_log_event)
        self._load_history()

    async def _load_history(self):
        try:
            client = get_client()
            resp = await client.get("/admin/api/logs", params={"lines": 200})
            lines = resp.json().get("lines", [])
            for line in lines:
                self._add_line(line.get("level", "INFO"), line.get("time", ""), line.get("message", ""))
            self.update()
        except Exception:
            pass

    def _on_log_event(self, data: dict):
        if self._paused:
            self._paused_count += 1
            self.pause_banner.content = ft.Text(f"已暂停 · 新 {self._paused_count} 条日志")
            return
        self._add_line(data.get("level", "INFO"), data.get("time", ""), data.get("message", ""))
        self.update()

    def _add_line(self, level: str, timestamp: str, message: str):
        row = build_log_row(level, timestamp, message)
        self._log_lines.append(row)
        self.log_list.controls.append(row)
        if len(self._log_lines) > 1000:
            old = self.log_list.controls[:200]
            for c in old:
                self.log_list.controls.remove(c)
            self._log_lines = self._log_lines[-800:]

    def _toggle_pause(self, e):
        self._paused = not self._paused
        self.pause_btn.icon = ft.icons.PLAY_ARROW if self._paused else ft.icons.PAUSE
        self.pause_banner.visible = self._paused
        self._paused_count = 0
        self.update()

    def _clear(self, e):
        self.log_list.controls.clear()
        self._log_lines.clear()
        self.update()
