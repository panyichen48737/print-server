"""Job history table with status badge."""
import flet as ft

def status_badge(status: str) -> ft.Container:
    colors = {
        "pending": ft.Colors.AMBER, "printing": ft.Colors.BLUE,
        "completed": ft.Colors.GREEN, "failed": ft.Colors.RED, "cancelled": ft.Colors.GREY,
    }
    return ft.Container(
        content=ft.Text(status, size=12, color=ft.Colors.WHITE),
        bgcolor=colors.get(status, ft.Colors.GREY),
        padding=ft.padding.symmetric(horizontal=8, vertical=2),
        border_radius=4,
    )

def build_job_rows(jobs: list[dict]) -> list[ft.DataRow]:
    return [
        ft.DataRow(cells=[
            ft.DataCell(ft.Text(str(j.get("id", "")))),
            ft.DataCell(ft.Text(j.get("filename", ""), max_lines=1)),
            ft.DataCell(status_badge(j.get("status", ""))),
            ft.DataCell(ft.Text(j.get("created_at", "")[-8:])),
        ]) for j in jobs
    ]
