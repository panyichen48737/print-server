"""Settings page with 7 config groups, save, and test notification."""
import flet as ft

from gui.components.notification import show_snackbar
from gui.http_client import get_client


class SettingsPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.fields: dict[str, ft.Control] = {}

        groups = [
            self._build_security_group(),
            self._build_print_defaults_group(),
            self._build_quark_group(),
            self._build_notification_group(),
            self._build_server_group(),
            self._build_worker_group(),
        ]

        self.content = ft.Column([
            ft.Text("设置", size=24, weight=ft.FontWeight.BOLD),
            *groups,
            ft.Row([
                ft.FilledButton("保存设置", on_click=self._save),
                ft.OutlinedButton("测试通知", on_click=self._test_notification),
                ft.Text("部分设置需要重启服务器后生效", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ]),
        ], spacing=16, scroll=ft.ScrollMode.AUTO)
        self._load()

    async def _load(self):
        try:
            client = get_client()
            resp = await client.get("/api/config")
            config = resp.json()
            for key, control in self.fields.items():
                if key in config:
                    if isinstance(control, (ft.TextField, ft.Dropdown)):
                        control.value = str(config[key])
                    elif isinstance(control, ft.Switch):
                        control.value = bool(config[key])
            self.update()
        except Exception as e:
            show_snackbar(self.page, f"加载配置失败: {e}", color=ft.Colors.RED)

    def _build_security_group(self) -> ft.Container:
        api_key = ft.TextField(label="api_key", password=True, width=400, can_reveal_password=True)
        self.fields["api_key"] = api_key
        return ft.Container(
            content=ft.Column([
                ft.Text("安全", weight=ft.FontWeight.BOLD, size=18),
                ft.Row([api_key, ft.IconButton(ft.icons.REFRESH, tooltip="生成新密钥")]),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_print_defaults_group(self) -> ft.Container:
        printer = ft.Dropdown(label="default_printer", width=300, options=[])
        copies = ft.TextField(
            label="default_copies", value="1", width=100, keyboard_type=ft.KeyboardType.NUMBER,
        )
        duplex = ft.Switch(label="default_duplex", value=True)
        color_sw = ft.Switch(label="default_color", value=True)
        paper = ft.Dropdown(
            label="paper_size", width=150,
            options=[
                ft.dropdown.Option("A4"),
                ft.dropdown.Option("Letter"),
                ft.dropdown.Option("A3"),
            ],
            value="A4",
        )
        excel_all = ft.Switch(label="excel_print_all_sheets", value=False)
        ppt_output = ft.Dropdown(
            label="ppt_output_type", width=200,
            options=[
                ft.dropdown.Option("slides"),
                ft.dropdown.Option("handout2"),
                ft.dropdown.Option("handout3"),
                ft.dropdown.Option("handout6"),
            ],
            value="slides",
        )
        auto_retry = ft.TextField(
            label="auto_retry_count", value="0", width=100, keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.fields.update({
            "default_printer": printer, "default_copies": copies,
            "default_duplex": duplex, "default_color": color_sw,
            "paper_size": paper, "excel_print_all_sheets": excel_all,
            "ppt_output_type": ppt_output, "auto_retry_count": auto_retry,
        })
        return ft.Container(
            content=ft.Column([
                ft.Text("打印默认值", weight=ft.FontWeight.BOLD, size=18),
                ft.Row([printer, copies, auto_retry]),
                ft.Row([duplex, color_sw, excel_all]),
                ft.Row([paper, ppt_output]),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_quark_group(self) -> ft.Container:
        key_id = ft.TextField(label="quark_api_key_id", password=True, width=400, can_reveal_password=True)
        key = ft.TextField(label="quark_api_key", password=True, width=400, can_reveal_password=True)
        self.fields.update({"quark_api_key_id": key_id, "quark_api_key": key})
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("夸克扫描王 API", weight=ft.FontWeight.BOLD, size=18),
                    ft.Container(
                        content=ft.Text("需重启", size=11),
                        bgcolor=ft.Colors.AMBER_100,
                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        border_radius=4,
                    ),
                ]),
                ft.Text("配置后需重启服务器生效", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                key_id, key,
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_notification_group(self) -> ft.Container:
        channel = ft.Dropdown(
            label="notify_channel", width=200,
            options=[
                ft.dropdown.Option("disabled"),
                ft.dropdown.Option("dingtalk"),
                ft.dropdown.Option("bark"),
            ],
            value="disabled",
        )
        dt_webhook = ft.TextField(label="dingtalk_webhook", password=True, width=400, can_reveal_password=True)
        dt_level = ft.Dropdown(
            label="dingtalk_level", width=200,
            options=[
                ft.dropdown.Option("error"),
                ft.dropdown.Option("warning"),
                ft.dropdown.Option("info"),
            ],
            value="error",
        )
        bark_key = ft.TextField(label="bark_key", password=True, width=400, can_reveal_password=True)
        bark_server = ft.TextField(label="bark_server", width=400, hint_text="https://api.day.app")
        self.fields.update({
            "notify_channel": channel, "dingtalk_webhook": dt_webhook,
            "dingtalk_level": dt_level, "bark_key": bark_key, "bark_server": bark_server,
        })
        return ft.Container(
            content=ft.Column([
                ft.Text("通知渠道", weight=ft.FontWeight.BOLD, size=18),
                channel, dt_webhook, dt_level, bark_key, bark_server,
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_server_group(self) -> ft.Container:
        port = ft.TextField(
            label="port", value="5000", width=150, keyboard_type=ft.KeyboardType.NUMBER,
        )
        log_level = ft.Dropdown(
            label="log_level", width=200,
            options=[
                ft.dropdown.Option("DEBUG"),
                ft.dropdown.Option("INFO"),
                ft.dropdown.Option("WARNING"),
                ft.dropdown.Option("ERROR"),
            ],
            value="INFO",
        )
        ssl = ft.Switch(label="ssl_enabled", value=False)
        self.fields.update({"port": port, "log_level": log_level, "ssl_enabled": ssl})
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("服务器", weight=ft.FontWeight.BOLD, size=18),
                    ft.Container(
                        content=ft.Text("需重启", size=11),
                        bgcolor=ft.Colors.AMBER_100,
                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        border_radius=4,
                    ),
                ]),
                ft.Row([port, log_level, ssl]),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_worker_group(self) -> ft.Container:
        field_defs = {
            "worker_count": "2", "max_file_size_mb": "100",
            "job_retention_days": "30", "print_dpi": "300",
            "job_timeout": "360", "word_timeout": "120",
        }
        controls = {}
        for key, default in field_defs.items():
            c = ft.TextField(
                label=key, value=default, width=150, keyboard_type=ft.KeyboardType.NUMBER,
            )
            controls[key] = c
            self.fields[key] = c
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Worker", weight=ft.FontWeight.BOLD, size=18),
                    ft.Container(
                        content=ft.Text("需重启", size=11),
                        bgcolor=ft.Colors.AMBER_100,
                        padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        border_radius=4,
                    ),
                ]),
                ft.Row(list(controls.values())),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    async def _save(self, e):
        config = {}
        for key, control in self.fields.items():
            if isinstance(control, (ft.TextField, ft.Switch, ft.Dropdown)):
                config[key] = control.value
        try:
            client = get_client()
            resp = await client.post("/api/config/save", json=config)
            if resp.status_code == 200:
                show_snackbar(self.page, "设置已保存")
                restart_keys = {
                    "port", "log_level", "ssl_enabled",
                    "quark_api_key_id", "quark_api_key",
                    "worker_count", "job_timeout",
                }
                if restart_keys & set(config.keys()):
                    self.page.open(ft.AlertDialog(
                        title=ft.Text("需重启服务器"),
                        content=ft.Text("部分设置需要重启服务器才能生效。是否立即重启？"),
                        actions=[
                            ft.TextButton("稍后"),
                            ft.FilledButton("立即重启"),
                        ],
                    ))
            else:
                show_snackbar(self.page, f"保存失败: {resp.text}", color=ft.Colors.RED)
        except Exception as ex:
            show_snackbar(self.page, f"错误: {ex}", color=ft.Colors.RED)

    async def _test_notification(self, e):
        try:
            client = get_client()
            await client.post("/api/test_notification")
            show_snackbar(self.page, "测试通知已发送")
        except Exception as ex:
            show_snackbar(self.page, f"发送失败: {ex}", color=ft.Colors.RED)
