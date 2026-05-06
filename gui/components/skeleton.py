"""Skeleton loading placeholders."""
import flet as ft


def card_skeleton(width: int = 200, height: int = 120):
    return ft.Container(
        width=width, height=height,
        bgcolor=ft.Colors.GREY_300,
        border_radius=8,
        animate_opacity=ft.Animation(800, "ease"),
        opacity=0.3,
    )

def table_row_skeleton(count: int = 5):
    rows = []
    for _ in range(count):
        rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Container(width=80, height=16, bgcolor=ft.Colors.GREY_300, border_radius=4))
            for _ in range(6)
        ]))
    return rows
