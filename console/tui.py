"""控制台监控面板 — Textual 版（事件驱动，零轮询）"""

import asyncio
import webbrowser
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, RichLog, Static
from textual.worker import get_current_worker

from app.version import __version__

from .autostart import install_autostart, is_autostart_installed, uninstall_autostart
from .conflicts import get_local_ips
from .log_handler import LOG_BUFFER, LOG_EVENT


class StatusWidget(Static):
    """服务状态面板 — 直接检查 ServerHandle（无 HTTP 轮询）"""

    def __init__(self, server_handle, **kwargs):
        super().__init__(**kwargs)
        self._handle = server_handle

    def on_mount(self) -> None:
        self.run_worker(self._poll_loop(), exclusive=True)

    async def _poll_loop(self) -> None:
        worker = get_current_worker()
        while not worker.is_cancelled:
            await self._refresh()
            await asyncio.sleep(2)

    async def _refresh(self) -> None:
        alive = self._handle.is_running
        if not alive:
            self.update(
                f'[bold]iOS 云打印服务器[/bold] [dim]v{__version__}[/dim]\n\n'
                f'状态: [bold yellow]正在启动...[/bold yellow]\n'
                f'[dim]后台服务初始化中，请稍候[/dim]'
            )
            return
        port = self._handle.port or '-'
        proto = 'https' if self._handle.ssl_enabled else 'http'
        ips = await asyncio.to_thread(get_local_ips)
        ip_str = ips[0] if ips else '0.0.0.0'
        self.update(
            f'[bold]iOS 云打印服务器[/bold] [dim]v{__version__}[/dim]\n\n'
            f'状态: [bold green]运行中[/bold green]\n'
            f'端口: {port}\n'
            f'管理地址: [bold yellow]{proto}://{ip_str}:{port}[/bold yellow]\n\n'
            f'[dim]打印机状态与运行统计请访问 Web 管理页面[/dim]'
        )


class LogWidget(RichLog):
    """实时日志面板 — 事件驱动，仅新日志到达时刷新"""

    def on_mount(self) -> None:
        self.run_worker(self._watch_logs(), exclusive=True)

    async def _watch_logs(self) -> None:
        worker = get_current_worker()
        while not worker.is_cancelled:
            LOG_EVENT.wait(timeout=1)
            LOG_EVENT.clear()
            if worker.is_cancelled:
                break
            self.refresh_log()

    def refresh_log(self) -> None:
        self.clear()
        for line in list(LOG_BUFFER)[-30:]:
            self.write(line)


class TUI(App):
    """控制台监控面板 — 管理后台服务器"""

    TITLE = f'iOS 云打印服务器 v{__version__}'
    CSS = """
    Header {
        dock: top;
    }

    Footer {
        dock: bottom;
    }

    Screen {
        layout: grid;
        grid-size: 2;
        grid-columns: 1fr 2fr;
        grid-rows: auto 1fr;
    }

    StatusWidget {
        padding: 1;
        border: solid $primary;
        height: 100%;
    }

    #quick-links {
        padding: 1;
        border: solid $secondary;
        height: 100%;
    }

    #quick-links Static {
        margin-bottom: 1;
    }

    LogWidget {
        border: solid $surface;
        padding: 1;
        column-span: 2;
    }
    """

    BINDINGS: ClassVar = [
        Binding('s', 'start', '启动'),
        Binding('t', 'stop', '停止'),
        Binding('r', 'restart', '重启'),
        Binding('o', 'open_web', '后台'),
        Binding('u', 'toggle_autostart', '自启'),
        Binding('q', 'quit', '退出'),
    ]

    def __init__(self, server_handle=None, app=None, config=None, **kwargs):
        super().__init__(**kwargs)
        self._handle = server_handle
        self._app = app
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusWidget(server_handle=self._handle)
        yield Static(id='quick-links')
        yield LogWidget()
        yield Footer()

    def on_mount(self) -> None:
        self._update_quick_links()

    def _update_quick_links(self) -> None:
        autostart = is_autostart_installed()
        u_label = '卸载自启' if autostart else '注册自启'
        port = self._handle.port or 5000
        proto = 'https' if self._handle.ssl_enabled else 'http'
        ips = get_local_ips()
        ip_str = ips[0] if ips else '0.0.0.0'
        self.query_one('#quick-links').update(
            f'[bold]操作[/bold]\n\n'
            f'[bold cyan]S[/bold cyan]  启动\n'
            f'[bold cyan]T[/bold cyan]  停止\n'
            f'[bold cyan]R[/bold cyan]  重启\n'
            f'[bold cyan]O[/bold cyan]  打开管理后台\n'
            f'[bold cyan]U[/bold cyan]  {u_label}\n'
            f'[bold cyan]Q[/bold cyan]  退出\n\n'
            f'[bold]管理地址[/bold]\n'
            f'{proto}://{ip_str}:{port}/admin'
        )

    def action_start(self) -> None:
        if self._handle.is_running:
            self.notify('服务器已在运行', severity='information')
            return
        ok = self._handle.start(self._app, self._config)
        self._update_quick_links()
        self.notify('服务器已启动' if ok else '启动失败', severity='information' if ok else 'error')

    def action_stop(self) -> None:
        self._handle.stop()
        self._update_quick_links()
        self.notify('服务器已停止', severity='information')

    def action_restart(self) -> None:
        self._handle.stop()
        ok = self._handle.start(self._app, self._config)
        self._update_quick_links()
        self.notify('服务器已重启' if ok else '重启失败', severity='information' if ok else 'error')

    def action_open_web(self) -> None:
        port = self._handle.port or 5000
        webbrowser.open(f'http://127.0.0.1:{port}/admin')
        self.notify('已在浏览器打开管理后台', severity='information')

    def action_toggle_autostart(self) -> None:
        if is_autostart_installed():
            ok, msg = uninstall_autostart()
        else:
            ok, msg = install_autostart()
        self._update_quick_links()
        self.notify(msg, severity='information' if ok else 'error')
