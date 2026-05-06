"""Reusable confirmation dialog."""
import flet as ft

def confirm_dialog(title: str, message: str, confirm_text: str = "确认",
                   on_confirm=None, on_cancel=None) -> ft.AlertDialog:
    return ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton("取消", on_click=lambda _: on_cancel() if on_cancel else None),
            ft.FilledButton(confirm_text, on_click=lambda _: on_confirm() if on_confirm else None),
        ],
    )
