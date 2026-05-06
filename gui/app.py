"""Main Flet application with NavigationRail, routing, and system tray."""
import asyncio
import threading

import flet as ft

from gui.child_process import ChildProcess
from gui.sse_client import sse
from gui.theme import build_theme
from gui.window_state import load_state, save_state

child = ChildProcess()


def _build_page(index: int, page: ft.Page) -> ft.Control:
    if index == 0:
        from gui.pages.dashboard import DashboardPage
        return DashboardPage(page)
    if index == 1:
        from gui.pages.quick_print import QuickPrintPage
        return QuickPrintPage(page)
    if index == 2:
        from gui.pages.job_manager import JobManagerPage
        return JobManagerPage(page)
    if index == 3:
        from gui.pages.logs import LogsPage
        return LogsPage(page)
    if index == 4:
        from gui.pages.settings import SettingsPage
        return SettingsPage(page)
    if index == 5:
        from gui.pages.printer_manager import PrinterManagerPage
        return PrinterManagerPage(page)
    if index == 6:
        from gui.pages.about import AboutPage
        return AboutPage(page)
    return ft.Text("未知页面")


def main(page: ft.Page):
    page.title = "iOS 云打印服务器"
    page.theme = build_theme(ft.ThemeMode.SYSTEM)
    page.theme_mode = ft.ThemeMode.SYSTEM

    # Window config
    page.window.width = 1200
    page.window.height = 800
    page.window.min_width = 900
    page.window.min_height = 600
    page.window.center()

    # Load saved window state
    saved_page = load_state(page)

    # Navigation state
    nav: ft.NavigationRail | None = None

    # Content area
    content_area = ft.Column(expand=True)

    def navigate(index: int):
        page._active_index = index  # type: ignore
        content_area.controls.clear()
        content_area.controls.append(_build_page(index, page))
        content_area.update()

    # Keyboard shortcuts
    def on_keyboard(e: ft.KeyboardEvent):
        shortcuts = {"1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6}
        if e.ctrl and e.key in shortcuts:
            nav.selected_index = shortcuts[e.key]
            navigate(nav.selected_index)
            page.update()
        elif e.ctrl and e.key.lower() == "p":
            nav.selected_index = 1
            navigate(1)
            page.update()
        elif e.key == "F5":
            navigate(nav.selected_index)
            page.update()

    page.on_keyboard_event = on_keyboard

    # Window close → minimize to tray (save state first)
    def on_window_event(e: ft.WindowEvent):
        if e.type == ft.WindowEventType.CLOSE:
            save_state(page)
            page.window.visible = False
            page.update()

    page.window.on_event = on_window_event

    # Show window from tray helper
    def _show_window():
        page.window.visible = True
        page.update()

    def _quit_app():
        child.stop()
        sse.stop()
        page.window.destroy()

    nav = ft.NavigationRail(
        selected_index=saved_page,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        destinations=[
            ft.NavigationRailDestination(icon=ft.icons.DASHBOARD, label="仪表盘"),
            ft.NavigationRailDestination(icon=ft.icons.PRINT, label="快速打印"),
            ft.NavigationRailDestination(icon=ft.icons.LIST_ALT, label="任务管理"),
            ft.NavigationRailDestination(icon=ft.icons.TERMINAL, label="实时日志"),
            ft.NavigationRailDestination(icon=ft.icons.SETTINGS, label="设置"),
            ft.NavigationRailDestination(icon=ft.icons.PRINTER, label="打印机"),
            ft.NavigationRailDestination(icon=ft.icons.INFO_OUTLINE, label="关于"),
        ],
        on_change=lambda e: navigate(int(e.control.selected_index)),
    )

    page.add(ft.Row([nav, ft.VerticalDivider(width=1), content_area], expand=True))

    # Start child process (headless server)
    child.start()
    sse.start()

    # Health check loop in background thread
    def health_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            child.health_loop(
                lambda msg: page.run_thread(
                    lambda: _show_snackbar(page, msg, ft.Colors.RED)
                )
            )
        )
        loop.close()

    threading.Thread(target=health_loop, daemon=True).start()

    navigate(saved_page)
    page.update()


def _show_snackbar(page: ft.Page, message: str, color: str = ft.Colors.GREEN):
    snack = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=color,
        duration=3000,
        open=True,
    )
    page.overlay.append(snack)
    page.update()
