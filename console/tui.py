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
from .daemon_manager import (
    is_daemon_alive,
    read_daemon_status,
    restart_daemon,
    start_daemon,
    stop_daemon,
)
from .log_handler import LOG_BUFFER, LOG_EVENT


class StatusWidget(Static):
    """服务状态面板 — 后台线程每 2s 刷新一次（阻塞调用在线程中执行）"""

    def on_mount(self) -> None:
        self.run_worker(self._poll_loop(), exclusive=True)

    async def _poll_loop(self) -> None:
        worker = get_current_worker()
        while not worker.is_cancelled:
            await self._refresh_async()
            await worker.sleep(2)

    async def _refresh_async(self) -> None:
        """在线程中执行阻塞的健康检查，不阻塞事件循环"""
        alive = await asyncio.to_thread(is_daemon_alive)
        if not alive:
            self.update(
                f'[bold]iOS 云打印服务器[/bold] [dim]v{__version__}[/dim]\n\n'
                f'状态: [bold yellow]正在启动...[/bold yellow]\n'
                f'[dim]后台服务初始化中，请稍候[/dim]'
            )
            return
        status = await asyncio.to_thread(read_daemon_status)
        port = status.get('port', '-')
        pid = status.get('pid', '-')
        ips = await asyncio.to_thread(get_local_ips)
        ip_str = ips[0] if ips else '0.0.0.0'
        self.update(
            f'[bold]iOS 云打印服务器[/bold] [dim]v{__version__}[/dim]\n\n'
            f'状态: [bold green]运行中[/bold green]\n'
            f'PID: {pid}    端口: {port}\n'
            f'管理地址: [bold yellow]{"https" if status.get("ssl", False) else "http"}://{ip_str}:{port}[/bold yellow]\n\n'
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
    """控制台监控面板 — 管理后台守护进程"""

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

    BINDINGS: ClassVar[list[Binding]] = [
        Binding('s', 'start', '启动'),
        Binding('t', 'stop', '停止'),
        Binding('r', 'restart', '重启'),
        Binding('o', 'open_web', '后台'),
        Binding('u', 'toggle_autostart', '自启'),
        Binding('q', 'quit', '退出'),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusWidget()
        yield Static(id='quick-links')
        yield LogWidget()
        yield Footer()

    def on_mount(self) -> None:
        self._update_quick_links()

    def _update_quick_links(self) -> None:
        autostart = is_autostart_installed()
        u_label = '卸载自启' if autostart else '注册自启'
        status = read_daemon_status()
        port = status.get('port', 5000)
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
            f'{"https" if status.get("ssl", False) else "http"}://{ip_str}:{port}/admin'
        )

    def action_start(self) -> None:
        ok, msg = start_daemon()
        self._update_quick_links()
        self.notify(msg, severity='information' if ok else 'error')

    def action_stop(self) -> None:
        ok, msg = stop_daemon()
        self._update_quick_links()
        self.notify(msg, severity='information' if ok else 'error')

    def action_restart(self) -> None:
        ok, msg = restart_daemon()
        self._update_quick_links()
        self.notify(msg, severity='information' if ok else 'error')

    def action_open_web(self) -> None:
        status = read_daemon_status()
        port = status.get('port', 5000)
        webbrowser.open(f'http://127.0.0.1:{port}/admin')
        self.notify('已在浏览器打开管理后台', severity='information')

    def action_toggle_autostart(self) -> None:
        if is_autostart_installed():
            ok, msg = uninstall_autostart()
        else:
            ok, msg = install_autostart()
        self._update_quick_links()
        self.notify(msg, severity='information' if ok else 'error')
