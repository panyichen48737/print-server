import threading
import msvcrt
import sys
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .conflicts import get_local_ips, cleanup_pid
from .log_handler import LOG_BUFFER
from .controller import ServerState, get_autostart_key, install_autostart, uninstall_autostart


class TUI:
    """控制台 TUI 渲染 + 键盘循环 + 保活"""

    def __init__(self, controller):
        self.ctrl = controller
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
            Layout(name="stats", size=48),
            Layout(name="log", ratio=1),
        )
        return layout

    def _render_header(self):
        state = self.ctrl.status
        port = self.ctrl.port
        autostart = get_autostart_key()
        autostart_str = "✔ 已自启" if autostart else "✘ 未自启"
        autostart_style = "green" if autostart else "red"
        if state == ServerState.RUNNING:
            status_style = "bold green"
            status_text = "● 运行中"
            ips = get_local_ips()
            ip_str = ips[0] if ips else "0.0.0.0"
            extra = f" 管理地址: [bold yellow]http://{ip_str}:{port}[/bold yellow]"
        elif state == ServerState.CRASHED:
            status_style = "bold yellow"
            status_text = "● 已崩溃 (自动恢复中...)"
            extra = f" 端口: {port}"
        else:
            status_style = "bold red"
            status_text = "● 已停止"
            extra = f" 端口: {port}"

        return Panel(
            Text.assemble(
                ("iOS 云打印服务器", "bold white"), "\n",
                ("状态: ", "cyan"), (status_text, status_style),
                ("  |  ", "dim"), extra,
                ("  |  ", "dim"), (f"自启: {autostart_str}", autostart_style),
            ),
            title="控制台",
            border_style="bright_blue",
        )

    def _render_stats(self):
        stats = self.ctrl.stats
        t = Table(show_header=False, border_style="blue", box=None, padding=(0, 2))
        t.add_column("指标", style="cyan")
        t.add_column("值", style="white")
        t.add_row("队列中", str(stats.get('queued', 0)))
        t.add_row("打印中", str(stats.get('printing', 0)))
        t.add_row("今日成功", str(stats.get('today_completed', 0)))
        t.add_row("今日失败", str(stats.get('today_failed', 0)))
        t.add_row("成功率", f"{stats.get('success_rate', 100):.0f}%")
        return Panel(t, title="运行统计", border_style="green")

    def _render_log(self):
        lines = LOG_BUFFER[-50:] if LOG_BUFFER else ["等待日志..."]
        return Panel("\n".join(lines), title="日志", border_style="dim")

    def _render_footer(self):
        autostart = get_autostart_key()
        u_label = "卸载自启" if autostart else "注册自启"
        return Panel(
            f"  [bold cyan]S[/bold cyan] 启动/停止    [bold cyan]R[/bold cyan] 重载配置    "
            f"[bold cyan]U[/bold cyan] {u_label}    [bold cyan]Q[/bold cyan] 退出",
            title="操作", border_style="yellow",
        )

    def _update(self):
        self.layout["header"].update(self._render_header())
        self.layout["stats"].update(self._render_stats())
        self.layout["log"].update(self._render_log())
        self.layout["footer"].update(self._render_footer())

    def run(self):
        """主循环：渲染 + 键盘处理 + 保活"""
        with Live(self.layout, console=self.console, refresh_per_second=2, screen=True):
            while True:
                # 保活：检测到崩溃自动重启
                if self.ctrl.status == ServerState.CRASHED:
                    self.ctrl.restart()

                self._update()

                if msvcrt.kbhit():
                    key = msvcrt.getch().lower()
                    if key == b'q':
                        self.ctrl.stop()
                        self.ctrl.queue_mgr.shutdown()
                        cleanup_pid()
                        sys.exit(0)
                    elif key == b's':
                        if self.ctrl.status == ServerState.RUNNING:
                            self.ctrl.stop()
                        else:
                            self.ctrl.start()
                    elif key == b'r':
                        self.ctrl.reload_config()
                    elif key == b'u':
                        if get_autostart_key():
                            uninstall_autostart()
                            LOG_BUFFER.append('已卸载开机自启')
                        else:
                            install_autostart()
                            LOG_BUFFER.append('已注册开机自启')

                threading.Event().wait(0.5)
