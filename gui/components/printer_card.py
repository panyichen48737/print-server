"""Printer status card with color indicator."""
import flet as ft

import gui.theme as _gui_theme


def status_color(overall: str) -> str:
    light = {"ready": ft.Colors.GREEN, "busy": ft.Colors.AMBER,
             "error": ft.Colors.RED, "offline": ft.Colors.GREY}
    dark = {"ready": "#4ADE80", "busy": "#FBBF24",
            "error": "#F87171", "offline": "#9CA3AF"}
    return (dark if _gui_theme._IS_DARK else light).get(overall, ft.Colors.GREY)

class PrinterCard(ft.Container):
    def __init__(self, name: str, overall: str, statuses: list[dict] | None = None,
                 is_default: bool = False, on_set_default=None):
        color = status_color(overall)
        status_lines = []
        for s in (statuses or []):
            status_lines.append(ft.Text(f"  {s.get('key', '')}: {s.get('label', '')}", size=12))
        super().__init__()
        self.content = ft.Column([
            ft.Row([
                ft.Container(width=12, height=12, bgcolor=color, border_radius=6),
                ft.Text(name, weight=ft.FontWeight.BOLD, size=16),
                ft.Text("默认" if is_default else "", size=12, color=ft.Colors.PRIMARY),
            ]),
            ft.Text(f"状态: {overall}", size=13, color=color),
            *status_lines,
            ft.ElevatedButton("设为默认", visible=not is_default,
                              on_click=self._make_set_default_handler(name, on_set_default)),
        ])
        self.padding = 16
        self.border_radius = 12
        self.bgcolor = ft.Colors.SURFACE

    def _make_set_default_handler(self, name: str, callback):
        if callback is None:
            return None
        async def handler(e):
            await callback(name)
        return handler
