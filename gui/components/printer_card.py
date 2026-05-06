"""Printer status card with color indicator."""
import flet as ft

def status_color(overall: str) -> str:
    return {"ready": ft.Colors.GREEN, "busy": ft.Colors.AMBER,
            "error": ft.Colors.RED, "offline": ft.Colors.GREY}.get(overall, ft.Colors.GREY)

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
                              on_click=lambda _: on_set_default(name) if on_set_default else None),
        ])
        self.padding = 16
        self.border_radius = 12
        self.bgcolor = ft.Colors.SURFACE
