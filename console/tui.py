"""控制台监控面板 — Textual 版"""
import webbrowser
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import Footer, Header, RichLog, Static

from app.version import __version__
from .conflicts import get_local_ips
from .log_handler import LOG_BUFFER
from .daemon_manager import (
    start_daemon,
    stop_daemon,
    restart_daemon,
    read_daemon_status,
    is_daemon_alive,
)
from .autostart import install_autostart, uninstall_autostart, is_autostart_installed


class StatusWidget(Static):
    """服务状态与快速入口面板"""
    alive: bool = reactive(False)
    port: Any = reactive("-")
    pid: Any = reactive("-")

    def watch_alive(self, value: bool) -> None:
        self.refresh_display()

    def on_mount(self) -> None:
        self.set_interval(0.25, self.refresh_display)

    def refresh_display(self) -> None:
        self.alive = is_daemon_alive()
        status = read_daemon_status()
        self.port = status.get("port", "-")
        self.pid = status.get("pid", "-")

        ips = get_local_ips()
        ip_str = ips[0] if ips else "0.0.0.0"
        status_text = "运行中" if self.alive else "已停止"
        status_style = "bold green" if self.alive else "bold red"

        self.update(
            f"[bold]iOS 云打印服务器[/bold] [dim]v{__version__}[/dim]\n\n"
            f"状态: [{status_style}]{status_text}[/{status_style}]\n"
            f"PID: {self.pid}    端口: {self.port}\n"
            f"管理地址: [bold yellow]http://{ip_str}:{self.port}[/bold yellow]\n\n"
            f"[dim]打印机状态与运行统计请访问 Web 管理页面[/dim]"
        )


class LogWidget(RichLog):
    """实时日志面板"""

    def on_mount(self) -> None:
        self.set_interval(0.25, self.refresh_log)

    def refresh_log(self) -> None:
        self.clear()
        for line in list(LOG_BUFFER)[-30:]:
            self.write(line)


class TUI(App):
    """控制台监控面板 — 管理后台守护进程"""

    TITLE = f"iOS 云打印服务器 v{__version__}"
    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
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

    Footer {
        column-span: 2;
    }
    """

    BINDINGS = [
        Binding("s", "start", "启动"),
        Binding("t", "stop", "停止"),
        Binding("r", "restart", "重启"),
        Binding("o", "open_web", "后台"),
        Binding("u", "toggle_autostart", "自启"),
        Binding("q", "quit", "退出"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusWidget()
        yield Static(id="quick-links")
        yield LogWidget()
        yield Footer()

    def on_mount(self) -> None:
        self._update_quick_links()

    def _update_quick_links(self) -> None:
        autostart = is_autostart_installed()
        u_label = "卸载自启" if autostart else "注册自启"
        status = read_daemon_status()
        port = status.get("port", 5000)
        ips = get_local_ips()
        ip_str = ips[0] if ips else "0.0.0.0"
        self.query_one("#quick-links").update(
            f"[bold]操作[/bold]\n\n"
            f"[bold cyan]S[/bold cyan]  启动\n"
            f"[bold cyan]T[/bold cyan]  停止\n"
            f"[bold cyan]R[/bold cyan]  重启\n"
            f"[bold cyan]O[/bold cyan]  打开管理后台\n"
            f"[bold cyan]U[/bold cyan]  {u_label}\n"
            f"[bold cyan]Q[/bold cyan]  退出\n\n"
            f"[bold]管理地址[/bold]\n"
            f"http://{ip_str}:{port}/admin"
        )

    def action_start(self) -> None:
        ok, msg = start_daemon()
        self._update_quick_links()
        self.notify(msg, severity="information" if ok else "error")

    def action_stop(self) -> None:
        ok, msg = stop_daemon()
        self._update_quick_links()
        self.notify(msg, severity="information" if ok else "error")

    def action_restart(self) -> None:
        ok, msg = restart_daemon()
        self._update_quick_links()
        self.notify(msg, severity="information" if ok else "error")

    def action_open_web(self) -> None:
        status = read_daemon_status()
        port = status.get("port", 5000)
        webbrowser.open(f"http://127.0.0.1:{port}/admin")
        self.notify("已在浏览器打开管理后台", severity="information")

    def action_toggle_autostart(self) -> None:
        if is_autostart_installed():
            ok, msg = uninstall_autostart()
        else:
            ok, msg = install_autostart()
        self._update_quick_links()
        self.notify(msg, severity="information" if ok else "error")
