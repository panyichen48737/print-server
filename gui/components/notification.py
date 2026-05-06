"""Snackbar notification wrapper."""
import flet as ft

def show_snackbar(page: ft.Page, message: str, color: str = ft.Colors.GREEN):
    page.snack_bar = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=color,
        duration=3000,
    )
    page.snack_bar.open = True
    page.update()
