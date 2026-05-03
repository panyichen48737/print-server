import threading
import time
import msvcrt
import sys

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from app.version import __version__
from .conflicts import get_local_ips
from .log_handler import LOG_BUFFER
from .daemon_manager import start_daemon, stop_daemon, restart_daemon, read_daemon_status, is_daemon_alive
from .autostart import install_autostart, uninstall_autostart, is_autostart_installed


class TUI:
    """控制台监控面板 — 管理后台守护进程"""

    def __init__(self):
        self.console = Console()
        self.layout = self._build_layout()

    def _build_layout(self):
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="log", ratio=1),
        )
        layout["left"].split_column(
            Layout(name="stats", size=10),
            Layout(name="printer", ratio=1),
        )
        return layout

    def _render_header(self):
        alive = is_daemon_alive()
        status = read_daemon_status()
        port = status.get('port', '-')
        pid = status.get('pid', '-')

        if alive:
            status_style = "bold green"
            status_text = "● 运行中"
            ips = get_local_ips()
            ip_str = ips[0] if ips else "0.0.0.0"
            extra = f" 管理地址: [bold yellow]http://{ip_str}:{port}[/bold yellow]"
        else:
            status_style = "bold red"
            status_text = "○ 已停止"
            extra = f" 端口: {port}"

        return Panel(
            Text.assemble(
                ("iOS 云打印服务器  ", "bold white"), (f"v{__version__}", "dim"), "\n",
                ("状态: ", "cyan"), (status_text, status_style),
                ("  |  ", "dim"), extra,
                ("  |  ", "dim"), (f"PID: {pid}", "cyan"),
            ),
            title="控制台",
            border_style="bright_blue",
        )

    def _render_stats(self):
        status = read_daemon_status()
        alive = is_daemon_alive()
        t = Table(show_header=False, border_style="blue", box=None, padding=(0, 2))
        t.add_column("项目", style="cyan")
        t.add_column("值", style="white")
        t.add_row("守护进程", "● 运行中" if alive else "○ 已停止")
        t.add_row("PID", str(status.get('pid', '-')))
        t.add_row("端口", str(status.get('port', '-')))
        return Panel(t, title="服务状态", border_style="green")

    def _render_printer_status(self):
        t = Table(show_header=False, border_style="blue", box=None, padding=(0, 2))
        t.add_column("项目", style="cyan")
        t.add_column("值", style="white")
        t.add_row("打印机", "请访问 Web 管理页面查看")
        t.add_row("运行统计", "请访问 Web 管理页面查看")
        t.add_row("", "")
        t.add_row("管理地址", f"[bold yellow]http://{get_local_ips()[0] if get_local_ips() else 'localhost'}:{read_daemon_status().get('port', '')}[/bold yellow]")
        return Panel(t, title="快速入口", border_style="cyan")

    def _render_log(self):
        if LOG_BUFFER:
            lines = list(LOG_BUFFER)[-30:]
        else:
            lines = ["等待日志..."]
        return Panel("\n".join(lines), title="日志", border_style="dim")

    def _render_footer(self):
        alive = is_daemon_alive()
        autostart = is_autostart_installed()
        u_label = "卸载自启" if autostart else "注册自启"
        return Panel(
            f"  [bold cyan]S[/bold cyan] 启动    "
            f"[bold cyan]T[/bold cyan] 停止    "
            f"[bold cyan]R[/bold cyan] 重启    "
            f"[bold cyan]U[/bold cyan] {u_label}    "
            f"[bold cyan]Q[/bold cyan] 退出（后台服务继续运行）",
            title="操作", border_style="yellow",
        )

    def _update(self):
        self.layout["header"].update(self._render_header())
        self.layout["stats"].update(self._render_stats())
        self.layout["printer"].update(self._render_printer_status())
        self.layout["log"].update(self._render_log())
        self.layout["footer"].update(self._render_footer())

    def run(self):
        with Live(self.layout, console=self.console, refresh_per_second=2, screen=True):
            while True:
                self._update()

                if msvcrt.kbhit():
                    key = msvcrt.getch().lower()
                    if key == b'q':
                        break
                    elif key == b's':
                        ok, msg = start_daemon()
                        LOG_BUFFER.append(msg)
                    elif key == b't':
                        ok, msg = stop_daemon()
                        LOG_BUFFER.append(msg)
                    elif key == b'r':
                        ok, msg = restart_daemon()
                        LOG_BUFFER.append(msg)
                    elif key == b'u':
                        if is_autostart_installed():
                            ok, msg = uninstall_autostart()
                        else:
                            ok, msg = install_autostart()
                        LOG_BUFFER.append(msg)

                time.sleep(0.5)
