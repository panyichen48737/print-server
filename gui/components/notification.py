"""Snackbar notification wrapper."""
import flet as ft


def show_snackbar(page: ft.Page, message: str, color: str = ft.Colors.GREEN):
    snack = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=color,
        duration=3000,
        open=True,
    )
    page.overlay.append(snack)
    page.update()
