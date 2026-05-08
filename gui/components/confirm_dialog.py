"""Reusable confirmation dialog."""
import flet as ft


def _make_handler(callback):
    if callback is None:
        return None
    async def handler(e):
        callback()
    return handler


def confirm_dialog(title: str, message: str, confirm_text: str = "确认",
                   on_confirm=None, on_cancel=None) -> ft.AlertDialog:
    return ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton("取消", on_click=_make_handler(on_cancel)),
            ft.FilledButton(confirm_text, on_click=_make_handler(on_confirm)),
        ],
    )
