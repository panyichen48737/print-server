"""Colored log entry."""
import flet as ft

import gui.theme as _gui_theme

LEVEL_COLORS_LIGHT = {
    "ERROR": ft.Colors.RED, "WARNING": ft.Colors.AMBER,
    "INFO": ft.Colors.BLUE, "DEBUG": ft.Colors.GREY,
}
LEVEL_COLORS_DARK = {
    "ERROR": "#F87171", "WARNING": "#FBBF24",
    "INFO": "#60A5FA", "DEBUG": "#9CA3AF",
}


def log_color(level: str) -> str:
    colors = LEVEL_COLORS_DARK if _gui_theme._IS_DARK else LEVEL_COLORS_LIGHT
    return colors.get(level, ft.Colors.ON_SURFACE)

def build_log_row(level: str, timestamp: str, message: str) -> ft.Row:
    return ft.Row([
        ft.Container(
            content=ft.Text(level, size=11, weight=ft.FontWeight.BOLD),
            bgcolor=log_color(level), padding=4, border_radius=2,
        ),
        ft.Text(timestamp, size=12, color=ft.Colors.ON_SURFACE_VARIANT, width=80),
        ft.Text(message, size=13, selectable=True, expand=True),
    ])
