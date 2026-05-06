"""Stats card with icon, number, and label."""
import flet as ft

class StatusCard(ft.Container):
    def __init__(self, label: str, value: str, icon: str, color: str = ft.Colors.PRIMARY):
        super().__init__()
        self.content = ft.Column([
            ft.Row([
                ft.Icon(icon, color=color, size=24),
                ft.Text(value, size=28, weight=ft.FontWeight.BOLD),
            ]),
            ft.Text(label, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
        ])
        self.padding = 16
        self.border_radius = 12
        self.bgcolor = ft.Colors.SURFACE
        self.shadow = ft.BoxShadow(blur_radius=4, color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK))
