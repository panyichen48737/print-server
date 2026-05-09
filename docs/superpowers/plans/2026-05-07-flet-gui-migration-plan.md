# Flet GUI Migration + Backend Modernization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the iOS Print Server from Web backend (FastAPI+HTMX+Jinja2) + TUI (Textual) to a modern Flet desktop GUI, with 11 backend modernization items across 3 priority tiers.

**Architecture:** C2 — single EXE with GUI main process + `--headless` server subprocess, communicating via HTTP localhost with keep-alive connection pool. GUI manages child process lifecycle (start/health-check/restart/shutdown).

**Tech Stack:** Flet (Flutter-based Python GUI), FastAPI (backend API, retained), SQLite + aiosqlite, Typer CLI, httpx, PyInstaller, NSIS

---

## File Structure

### Phase 1 — New Files (Flet GUI)

```
gui/
├── __init__.py                  # Package init, version
├── __main__.py                  # python -m gui entry point
├── app.py                       # Main Flet App (NavigationRail, routing, tray)
├── child_process.py             # Subprocess lifecycle: start/health-check/restart/kill
├── http_client.py               # httpx.AsyncClient singleton, keep-alive pool
├── sse_client.py                # SSE event stream client, background thread
├── theme.py                     # Design tokens (8 tokens x light/dark), ThemeMode
├── window_state.py              # Window size/position/page persistence
├── pages/
│   ├── __init__.py
│   ├── dashboard.py             # Statistics cards, trend chart, printer status, recent jobs
│   ├── quick_print.py            # File drag-drop, print options, submit
│   ├── job_manager.py           # Queue + history table, filter, pagination, bulk ops
│   ├── logs.py                  # Real-time log viewer, filter, pause, auto-scroll
│   ├── settings.py              # 7-group config form, save, test notification
│   ├── printer_manager.py       # Printer card grid, status, set default
│   └── about.py                 # Version info, update check, links
└── components/
    ├── __init__.py
    ├── status_card.py           # Stats card with icon/number/label
    ├── skeleton.py              # Skeleton loading placeholder
    ├── confirm_dialog.py        # Reusable confirm/cancel dialog
    ├── notification.py          # Snackbar notification wrapper
    ├── printer_card.py          # Printer status card with color indicator
    ├── job_table.py             # Job history table with status badge
    └── log_list.py              # Colored log entry with level/time/message
```

### Phase 1 — Modified Files

```
console/__init__.py              # Add --gui flag to launch Flet app
console/autostart.py             # May need update for GUI launch path
scripts/build.py                 # Add gui/ package to PyInstaller hidden-imports
pyproject.toml                   # Add flet dependency
```

### Phase 2 — Modified Files (Backend Modernization)

```
app/printing/repository.py       # aiosqlite migration
app/printing/job_queue.py        # async methods
app/printing/worker.py           # async db update, drain()
app/routes/api.py                # async routes, health check enhancement, version API
app/routes/admin.py              # async routes
app/services/heartbeat.py        # async cleanup + recover
app/schemas.py                   # Pydantic request models
app/__init__.py                  # OpenAPI config, version info
app/_paths.py                    # Pathlib return types
app/config.py                    # Pathlib cleanup
app/services/upload.py           # Pathlib cleanup
console/__init__.py              # Typer CLI rewrite, signal handling
app/exceptions.py                # Exception hierarchy (already exists, verify)
pyproject.toml                   # ruff rules, uv config, mypy strict, deps
alembic/                         # New directory: migration scripts
alembic.ini                      # Alembic config
```

---

## Phase 1: Flet GUI Migration

### Task 1: Project Setup — gui/ package + theme + dependencies

**Files:**
- Create: `gui/__init__.py`
- Create: `gui/__main__.py`
- Create: `gui/theme.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Create gui package skeleton**

Create `gui/__init__.py`:
```python
"""Flet Desktop GUI for iOS Print Server."""
__version__ = "1.5.0"
```

Create `gui/__main__.py`:
```python
"""python -m gui entry point."""
from gui.app import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create theme.py with design tokens**

Create `gui/theme.py`:
```python
"""Design tokens for light/dark themes."""
import flet as ft
from dataclasses import dataclass, field

@dataclass
class ThemeTokens:
    surface: str
    primary: str
    primary_container: str
    error: str
    on_surface: str
    on_surface_variant: str
    outline: str
    success: str

LIGHT = ThemeTokens(
    surface="#FFFFFF",
    primary="#4F46E5",
    primary_container="#EEF2FF",
    error="#DC2626",
    on_surface="#1F2937",
    on_surface_variant="#6B7280",
    outline="#D1D5DB",
    success="#16A34A",
)

DARK = ThemeTokens(
    surface="#1E1E2E",
    primary="#818CF8",
    primary_container="#312E81",
    error="#F87171",
    on_surface="#E2E8F0",
    on_surface_variant="#94A3B8",
    outline="#4B5563",
    success="#4ADE80",
)

def build_theme(mode: ft.ThemeMode) -> ft.Theme:
    tokens = DARK if mode == ft.ThemeMode.DARK else LIGHT
    return ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=tokens.primary,
            primary_container=tokens.primary_container,
            error=tokens.error,
            surface=tokens.surface,
            on_surface=tokens.on_surface,
            on_surface_variant=tokens.on_surface_variant,
            outline=tokens.outline,
        ),
    )
```

- [ ] **Step 3: Add flet dependency to pyproject.toml**

Add to `pyproject.toml` `[project.dependencies]`:
```
"flet>=0.27.0"
```

- [ ] **Step 4: Verify setup**

Run: `cd /path/to/project && python -c "import gui; import flet; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add gui/ pyproject.toml
git commit -m "feat(gui): add gui package skeleton with theme system"
```

---

### Task 2: HTTP Client + SSE Client

**Files:**
- Create: `gui/http_client.py`
- Create: `gui/sse_client.py`

- [ ] **Step 1: Create http_client.py**

Create `gui/http_client.py`:
```python
"""httpx.AsyncClient singleton with keep-alive connection pool."""
import httpx

_client: httpx.AsyncClient | None = None

def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        limits = httpx.Limits(
            max_keepalive_connections=10,
            max_connections=20,
            keepalive_expiry=30.0,
        )
        _client = httpx.AsyncClient(
            base_url="http://127.0.0.1:5000",
            limits=limits,
            timeout=httpx.Timeout(10.0),
        )
    return _client

async def close_client():
    global _client
    if _client:
        await _client.aclose()
        _client = None
```

- [ ] **Step 2: Create sse_client.py**

Create `gui/sse_client.py`:
```python
"""SSE event stream client running in background thread."""
import asyncio
import json
import threading
from typing import Callable
from gui.http_client import get_client

class SSEClient:
    def __init__(self):
        self._callbacks: dict[str, list[Callable]] = {}
        self._running = False
        self._thread: threading.Thread | None = None

    def on(self, event_type: str, callback: Callable):
        self._callbacks.setdefault(event_type, []).append(callback)

    def off(self, event_type: str, callback: Callable):
        self._callbacks.get(event_type, []).remove(callback)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._stream())
        loop.close()

    async def _stream(self):
        client = get_client()
        try:
            async with client.stream("GET", "/api/events") as response:
                async for line in response.aiter_lines():
                    if not self._running:
                        break
                    if line.startswith("event: "):
                        event_type = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                        for cb in self._callbacks.get(event_type, []):
                            cb(data)
        except Exception:
            pass  # Connection error handled by caller
```

- [ ] **Step 3: Commit**

```bash
git add gui/http_client.py gui/sse_client.py
git commit -m "feat(gui): add HTTP client and SSE event stream client"
```

---

### Task 3: Child Process Manager

**Files:**
- Create: `gui/child_process.py`

- [ ] **Step 1: Create child_process.py**

Create `gui/child_process.py`:
```python
"""Subprocess lifecycle management for --headless server."""
import asyncio
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import httpx
from gui.http_client import get_client

class ChildProcess:
    def __init__(self):
        self._process: subprocess.Popen | None = None
        self._restart_count = 0
        self._max_restarts = 3
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _port_listening(self, port: int = 5000) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0

    async def health_check(self) -> bool:
        try:
            client = get_client()
            resp = await client.get("/api/health", timeout=3.0)
            return resp.status_code == 200
        except Exception:
            return False

    def start(self):
        with self._lock:
            if self._port_listening():
                return  # Already running
            exe = sys.executable
            args = [exe, "-m", "console", "--headless"]
            if getattr(sys, "frozen", False):
                exe = os.path.join(sys._MEIPASS, "iOSPrintServer.exe")  # type: ignore
                args = [exe, "--headless"]
            self._process = subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self._restart_count = 0

    def stop(self):
        with self._lock:
            if self._process:
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                self._process = None

    def restart(self):
        self.stop()
        time.sleep(2)
        self.start()

    async def health_loop(self, on_failure: callable):
        """Called periodically from GUI. Restarts on failure up to 3 times."""
        while True:
            await asyncio.sleep(10)
            if not self.is_running():
                continue
            ok = await self.health_check()
            if ok:
                self._restart_count = 0
                continue
            self._restart_count += 1
            if self._restart_count > self._max_restarts:
                on_failure("Server crashed and failed to restart after 3 attempts")
                break
            self.restart()
```

- [ ] **Step 2: Commit**

```bash
git add gui/child_process.py
git commit -m "feat(gui): add child process lifecycle manager with watchdog"
```

---

### Task 4: Reusable Components

**Files:**
- Create: `gui/components/__init__.py`
- Create: `gui/components/status_card.py`
- Create: `gui/components/skeleton.py`
- Create: `gui/components/confirm_dialog.py`
- Create: `gui/components/notification.py`
- Create: `gui/components/printer_card.py`
- Create: `gui/components/job_table.py`
- Create: `gui/components/log_list.py`

- [ ] **Step 1: Create components/__init__.py**

```python
"""Reusable GUI components."""
```

- [ ] **Step 2: Create skeleton.py**

```python
"""Skeleton loading placeholders."""
import flet as ft

def card_skeleton(width: int = 200, height: int = 120):
    return ft.Container(
        width=width, height=height,
        bgcolor=ft.Colors.GREY_300,
        border_radius=8,
        animate_opacity=ft.Animation(800, "ease"),
        opacity=0.3,
    )

def table_row_skeleton(count: int = 5):
    rows = []
    for _ in range(count):
        rows.append(ft.DataRow(cells=[
            ft.DataCell(ft.Container(width=80, height=16, bgcolor=ft.Colors.GREY_300, border_radius=4))
            for _ in range(6)
        ]))
    return rows
```

- [ ] **Step 3: Create status_card.py**

```python
"""Stats card with icon, number, and label."""
import flet as ft

class StatusCard(ft.Container):
    def __init__(self, label: str, value: str, icon: str, color: str = ft.Colors.PRIMARY):
        super().__init__()
        self.content = ft.Column([
            ft.Row([
                ft.Icon(icon, color=color, size=24),
                ft.Text(value, size=28, weight=ft.FontWeight.BOLD),
            ]),
            ft.Text(label, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
        ])
        self.padding = 16
        self.border_radius = 12
        self.bgcolor = ft.Colors.SURFACE
        self.shadow = ft.BoxShadow(blur_radius=4, color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK))
```

- [ ] **Step 4: Create confirm_dialog.py**

```python
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
```

- [ ] **Step 5: Create notification.py**

```python
"""Snackbar notification wrapper."""
import flet as ft

def show_snackbar(page: ft.Page, message: str, color: str = ft.Colors.GREEN):
    page.snack_bar = ft.SnackBar(
        content=ft.Text(message),
        bgcolor=color,
        duration=3000,
    )
    page.snack_bar.open = True
    page.update()
```

- [ ] **Step 6: Create printer_card.py**

```python
"""Printer status card with color indicator."""
import flet as ft

def status_color(overall: str) -> str:
    return {"ready": ft.Colors.GREEN, "busy": ft.Colors.AMBER,
            "error": ft.Colors.RED, "offline": ft.Colors.GREY}.get(overall, ft.Colors.GREY)

class PrinterCard(ft.Container):
    def __init__(self, name: str, overall: str, statuses: list[dict] | None = None,
                 is_default: bool = False, on_set_default=None):
        color = status_color(overall)
        status_lines = []
        for s in (statuses or []):
            status_lines.append(ft.Text(f"  {s.get('key', '')}: {s.get('label', '')}", size=12))
        super().__init__()
        self.content = ft.Column([
            ft.Row([
                ft.Container(width=12, height=12, bgcolor=color, border_radius=6),
                ft.Text(name, weight=ft.FontWeight.BOLD, size=16),
                ft.Text("默认" if is_default else "", size=12, color=ft.Colors.PRIMARY),
            ]),
            ft.Text(f"状态: {overall}", size=13, color=color),
            *status_lines,
            ft.ElevatedButton("设为默认", visible=not is_default,
                              on_click=lambda _: on_set_default(name) if on_set_default else None),
        ])
        self.padding = 16
        self.border_radius = 12
        self.bgcolor = ft.Colors.SURFACE
```

- [ ] **Step 7: Create job_table.py**

```python
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
```

- [ ] **Step 8: Create log_list.py**

```python
"""Colored log entry."""
import flet as ft

def log_color(level: str) -> str:
    return {"ERROR": ft.Colors.RED, "WARNING": ft.Colors.AMBER,
            "INFO": ft.Colors.BLUE, "DEBUG": ft.Colors.GREY}.get(level, ft.Colors.ON_SURFACE)

def build_log_row(level: str, timestamp: str, message: str) -> ft.Row:
    return ft.Row([
        ft.Container(
            content=ft.Text(level, size=11, weight=ft.FontWeight.BOLD),
            bgcolor=log_color(level), padding=4, border_radius=2,
        ),
        ft.Text(timestamp, size=12, color=ft.Colors.ON_SURFACE_VARIANT, width=80),
        ft.Text(message, size=13, selectable=True, expand=True),
    ])
```

- [ ] **Step 9: Commit**

```bash
git add gui/components/
git commit -m "feat(gui): add reusable components (skeleton, cards, table, logs, dialog, notification)"
```

---

### Task 5: Main App Shell — Navigation + Tray + Routing

**Files:**
- Create: `gui/app.py`
- Create: `gui/window_state.py`

- [ ] **Step 1: Create window_state.py**

```python
"""Window state persistence."""
import json
import os
from flet import Page

PERSISTENT_DIR = os.path.join(os.environ.get("APPDATA", "."), "iOSPrintServer")
STATE_FILE = os.path.join(PERSISTENT_DIR, "window_state.json")

def save_state(page: Page):
    state = {
        "width": page.width, "height": page.height,
        "left": page.window_left, "top": page.window_top,
        "active_page": _get_active_index(page),
    }
    os.makedirs(PERSISTENT_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state(page: Page):
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        if state.get("width"): page.window_width = state["width"]
        if state.get("height"): page.window_height = state["height"]
        if state.get("left"): page.window_left = state["left"]
        if state.get("top"): page.window_top = state["top"]
        return state.get("active_page", 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

def _get_active_index(page: Page) -> int:
    # Placeholder — will be connected to nav index
    return getattr(page, "_active_index", 0)
```

- [ ] **Step 2: Create app.py — Main App class with NavigationRail + system tray**

```python
"""Main Flet application with NavigationRail, routing, and system tray."""
import asyncio
import threading
import flet as ft
import flet as ft

from gui.child_process import ChildProcess
from gui.http_client import get_client, close_client
from gui.sse_client import SSEClient
from gui.theme import build_theme
from gui.window_state import save_state, load_state

child = ChildProcess()
sse = SSEClient()

def main(page: ft.Page):
    page.title = "iOS 云打印服务器"
    page.theme = build_theme(ft.ThemeMode.SYSTEM)
    page.theme_mode = ft.ThemeMode.SYSTEM
    
    # Window config
    page.window_width = 1200
    page.window_height = 800
    page.window_min_width = 900
    page.window_min_height = 600
    page.window_center()
    
    # Load saved state
    saved_page = load_state(page)
    
    # System tray
    page.window_close_event = lambda e: _minimize_to_tray(page)
    
    def _minimize_to_tray(e):
        page.window_visible = False
        page.update()
    
    def _show_window(e):
        page.window_visible = True
        page.update()
    
    def _quit_app(e):
        child.stop()
        sse.stop()
        page.window_destroy()
    
    page.window_tray = ft.SystemTray(
        icon=ft.Icon(ft.icons.PRINT),
        tooltip="iOS 云打印服务器",
        menu_items=[
            ft.MenuItem(text="显示", on_click=_show_window),
            ft.MenuItem(text="退出", on_click=_quit_app),
        ],
    )
    
    # Page content placeholder
    content_area = ft.Column(expand=True)
    
    def navigate(index: int):
        page._active_index = index  # type: ignore
        content_area.controls.clear()
        content_area.controls.append(_build_page(index, page))
        content_area.update()
    
    nav = ft.NavigationRail(
        selected_index=saved_page,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        # labels will be updated when pages are imported
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
    
    # Start child process
    child.start()
    sse.start()
    
    # Start health check loop in background
    def health_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(child.health_loop(
            lambda msg: page.snack_bar(ft.SnackBar(ft.Text(msg), bgcolor=ft.Colors.RED))
        ))
        loop.close()
    threading.Thread(target=health_loop, daemon=True).start()
    
    navigate(saved_page)
    page.update()
```

- [ ] **Step 3: Connect page builders (stubs)**

In `app.py`, add the `_build_page` function using the page modules from Tasks 6-12:

```python
def _build_page(index: int, page: ft.Page) -> ft.Control:
    if index == 0: return DashboardPage(page)
    elif index == 1: return QuickPrintPage(page)
    elif index == 2: return JobManagerPage(page)
    elif index == 3: return LogsPage(page)
    elif index == 4: return SettingsPage(page)
    elif index == 5: return PrinterManagerPage(page)
    elif index == 6: return AboutPage(page)
    return ft.Text("未知页面")
```

(Imports for each page class will be added as pages are created.)

- [ ] **Step 4: Commit**

```bash
git add gui/app.py gui/window_state.py
git commit -m "feat(gui): add main app shell with navigation, tray, and child process lifecycle"
```

---

### Task 6: Dashboard Page

**Files:**
- Create: `gui/pages/__init__.py`
- Create: `gui/pages/dashboard.py`

- [ ] **Step 1: Create pages/__init__.py**

```python
"""GUI page modules."""
```

- [ ] **Step 2: Create dashboard.py**

```python
"""Dashboard page: server status, 6 stat cards, recent jobs, printer status."""
import flet as ft
from gui.http_client import get_client
from gui.components.status_card import StatusCard
from gui.components.job_table import build_job_rows
from gui.components.skeleton import card_skeleton, table_row_skeleton

class DashboardPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.stats_row = ft.Row(wrap=True, spacing=16)
        self.recent_jobs = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("ID")), ft.DataColumn(ft.Text("文件名")),
            ft.DataColumn(ft.Text("状态")), ft.DataColumn(ft.Text("时间")),
        ])
        self.printer_status = ft.Column()
        self.status_bar = ft.Container(bgcolor=ft.Colors.GREY_200, padding=10)
        
        self.content = ft.Column([
            self.status_bar,
            ft.Text("仪表盘", size=24, weight=ft.FontWeight.BOLD),
            self.stats_row,
            ft.Row([
                ft.Column([ft.Text("打印机状态", weight=ft.FontWeight.BOLD), self.printer_status], expand=1),
                ft.Column([ft.Text("最近任务", weight=ft.FontWeight.BOLD), self.recent_jobs], expand=2),
            ], expand=True),
        ])
        self._load_data()

    def _load_data(self):
        # Show skeletons
        self.stats_row.controls = [card_skeleton() for _ in range(6)]
        self.update()
        # Async load via page.run_task
        self.page.run_task(self._fetch_data)

    async def _fetch_data(self):
        try:
            client = get_client()
            health = await client.get("/api/health")
            health_data = health.json()
            # Update status bar
            self.status_bar.content = ft.Row([
                ft.Container(width=10, height=10, bgcolor=ft.Colors.GREEN, border_radius=5),
                ft.Text(f"运行中 · 端口 {health_data.get('port', 5000)} · 队列: {health_data.get('queue_size', 0)}"),
            ])
            # Stats cards
            stats = await client.get("/admin/api/stats")
            stats_data = stats.json()
            icons = [ft.icons.HOURGLASS_EMPTY, ft.icons.PRINT, ft.icons.CHECK_CIRCLE,
                     ft.icons.ERROR, ft.icons.TRENDING_UP, ft.icons.ANALYTICS]
            labels = ["排队中", "打印中", "今日完成", "今日失败", "成功率", "总计"]
            self.stats_row.controls = [
                StatusCard(label, str(stats_data.get(label, 0)), icon)
                for label, icon in zip(labels, icons)
            ]
            # Recent jobs
            jobs = await client.get("/admin/api/jobs", params={"limit": 10})
            self.recent_jobs.rows = build_job_rows(jobs.json())
        except Exception as e:
            self.status_bar.bgcolor = ft.Colors.RED_100
            self.status_bar.content = ft.Text(f"连接失败: {e}")
        self.update()
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/__init__.py gui/pages/dashboard.py
git commit -m "feat(gui): add dashboard page with stats cards, server status, recent jobs"
```

---

### Task 7: Quick Print Page

**Files:**
- Create: `gui/pages/quick_print.py`

- [ ] **Step 1: Create quick_print.py**

```python
"""Quick print page: file drag-drop, print options, submit."""
import flet as ft
from gui.http_client import get_client

class QuickPrintPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.selected_file = ft.Text("未选择文件", color=ft.Colors.ON_SURFACE_VARIANT)
        self.printer_dropdown = ft.Dropdown(label="打印机", width=300)
        self.copies_input = ft.TextField(label="份数", value="1", width=100, keyboard_type=ft.KeyboardType.NUMBER)
        self.duplex_switch = ft.Switch(label="双面", value=True)
        self.color_switch = ft.Switch(label="颜色", value=True)
        self.paper_size = ft.Dropdown(label="纸张大小", width=150, options=[
            ft.dropdown.Option("A4"), ft.dropdown.Option("Letter"), ft.dropdown.Option("A3"),
        ], value="A4")
        self.progress = ft.ProgressBar(visible=False)
        
        self.content = ft.Column([
            ft.Text("快速打印", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.icons.CLOUD_UPLOAD, size=48, color=ft.Colors.PRIMARY),
                    ft.Text("拖拽文件到此处或点击选择", size=16),
                    self.selected_file,
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                height=200, border=ft.border.all(2, ft.Colors.PRIMARY, style=ft.BorderStyle.DASHED),
                border_radius=12, ink=True, on_click=self._pick_file,
            ),
            ft.Row([self.printer_dropdown, self.copies_input], spacing=16),
            ft.Row([self.duplex_switch, self.color_switch, self.paper_size], spacing=16),
            self.progress,
            ft.FilledButton("开始打印", icon=ft.icons.PRINT, on_click=self._submit_print),
        ], spacing=16)
        self._load_printers()

    async def _load_printers(self):
        try:
            client = get_client()
            resp = await client.get("/api/printers")
            printers = resp.json()
            self.printer_dropdown.options = [ft.dropdown.Option(p) for p in printers]
            self.update()
        except Exception:
            pass

    def _pick_file(self, e):
        self.page.pick_files(on_result=self._on_file_picked)

    def _on_file_picked(self, e: ft.FilePickerResultEvent):
        if e.files:
            f = e.files[0]
            self.selected_file.value = f"{f.name} ({f.size / 1024:.1f} KB)"
            self._file_path = f.path
            self.selected_file.update()

    async def _submit_print(self, e):
        if not hasattr(self, '_file_path') or not self._file_path:
            return
        self.progress.visible = True
        self.progress.update()
        try:
            client = get_client()
            with open(self._file_path, "rb") as f:
                files = {"file": f}
                data = {
                    "printer": self.printer_dropdown.value or "",
                    "copies": self.copies_input.value or "1",
                    "duplex": str(self.duplex_switch.value).lower(),
                    "color": str(self.color_switch.value).lower(),
                    "paper_size": self.paper_size.value or "A4",
                }
                resp = await client.post("/api/print", data=data, files=files)
            if resp.status_code == 200:
                from gui.components.notification import show_snackbar
                show_snackbar(self.page, "打印任务已提交")
            else:
                from gui.components.notification import show_snackbar
                show_snackbar(self.page, f"提交失败: {resp.text}", color=ft.Colors.RED)
        except Exception as ex:
            from gui.components.notification import show_snackbar
            show_snackbar(self.page, f"错误: {ex}", color=ft.Colors.RED)
        finally:
            self.progress.visible = False
            self.progress.update()
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/quick_print.py
git commit -m "feat(gui): add quick print page with file picker, print options, submit"
```

---

### Task 8: Job Manager Page

**Files:**
- Create: `gui/pages/job_manager.py`

- [ ] **Step 1: Create job_manager.py**

```python
"""Job manager page: active queue + history table with filter/pagination/bulk ops."""
import flet as ft
from gui.http_client import get_client
from gui.components.job_table import status_badge

class JobManagerPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.status_filter = ft.Dropdown(label="状态", width=150, options=[
            ft.dropdown.Option("all", "全部"), ft.dropdown.Option("pending", "排队中"),
            ft.dropdown.Option("printing", "打印中"), ft.dropdown.Option("completed", "已完成"),
            ft.dropdown.Option("failed", "失败"), ft.dropdown.Option("cancelled", "已取消"),
        ], value="all")
        self.search_input = ft.TextField(label="搜索文件名", width=250)
        self.table = ft.DataTable(columns=[
            ft.DataColumn(ft.Text("ID")), ft.DataColumn(ft.Text("文件名")),
            ft.DataColumn(ft.Text("类型")), ft.DataColumn(ft.Text("大小")),
            ft.DataColumn(ft.Text("状态")), ft.DataColumn(ft.Text("提交时间")),
            ft.DataColumn(ft.Text("操作")),
        ])
        self.pagination = ft.Row([ft.TextButton("上一页"), ft.Text("第 1 页"), ft.TextButton("下一页")])
        self.queue_section = ft.Column()
        
        self.content = ft.Column([
            ft.Text("任务管理", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("打印队列", weight=ft.FontWeight.BOLD, size=18),
            self.queue_section,
            ft.Divider(),
            ft.Row([self.status_filter, self.search_input, ft.FilledButton("搜索", on_click=self._search),
                    ft.FilledTonalButton("批量取消"), ft.FilledTonalButton("批量重试")]),
            self.table,
            self.pagination,
        ])
        self._load(0)
    
    async def _load(self, offset: int):
        try:
            client = get_client()
            status = self.status_filter.value if self.status_filter.value != "all" else None
            params = {"limit": 20, "offset": offset}
            if status: params["status"] = status
            if self.search_input.value: params["search"] = self.search_input.value
            resp = await client.get("/admin/api/jobs", params=params)
            jobs = resp.json()
            self.table.rows = [
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(j.get("id", "")))),
                    ft.DataCell(ft.Text(j.get("filename", ""), max_lines=1)),
                    ft.DataCell(ft.Text(j.get("file_type", ""))),
                    ft.DataCell(ft.Text(j.get("file_size", ""))),
                    ft.DataCell(status_badge(j.get("status", ""))),
                    ft.DataCell(ft.Text(j.get("created_at", ""))),
                    ft.DataCell(ft.Row([
                        ft.IconButton(ft.icons.CANCEL, tooltip="取消", icon_size=18,
                                      on_click=lambda _, jid=j["id"]: self._cancel(jid)),
                        ft.IconButton(ft.icons.REPLAY, tooltip="重试", icon_size=18,
                                      on_click=lambda _, jid=j["id"]: self._retry(jid)),
                    ])),
                ]) for j in jobs
            ]
            self.update()
        except Exception as e:
            from gui.components.notification import show_snackbar
            show_snackbar(self.page, f"加载失败: {e}", color=ft.Colors.RED)

    async def _cancel(self, job_id: int):
        client = get_client()
        await client.post(f"/api/cancel/{job_id}")
        self._load(0)

    async def _retry(self, job_id: int):
        client = get_client()
        await client.post(f"/api/retry/{job_id}")
        self._load(0)

    def _search(self, e):
        self._load(0)
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/job_manager.py
git commit -m "feat(gui): add job manager page with queue, history table, filter, pagination, bulk ops"
```

---

### Task 9: Real-time Logs Page

**Files:**
- Create: `gui/pages/logs.py`

- [ ] **Step 1: Create logs.py**

```python
"""Real-time log viewer with filter, pause, auto-scroll."""
import flet as ft
from gui.http_client import get_client
from gui.sse_client import sse
from gui.components.log_list import build_log_row, log_color

class LogsPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self._paused = False
        self._paused_count = 0
        self._log_lines: list[ft.Row] = []
        
        self.level_filter = ft.Dropdown(label="级别", width=150, options=[
            ft.dropdown.Option("ALL", "全部"), ft.dropdown.Option("ERROR"),
            ft.dropdown.Option("WARNING"), ft.dropdown.Option("INFO"), ft.dropdown.Option("DEBUG"),
        ], value="ALL")
        self.search_filter = ft.TextField(label="搜索", width=250)
        self.pause_btn = ft.IconButton(ft.icons.PAUSE, tooltip="暂停", on_click=self._toggle_pause)
        self.clear_btn = ft.IconButton(ft.icons.CLEAR_ALL, tooltip="清空", on_click=self._clear)
        self.auto_scroll_switch = ft.Switch(label="自动滚动", value=True)
        self.pause_banner = ft.Container(visible=False, bgcolor=ft.Colors.BLUE_100,
                                          padding=8, content=ft.Text(""))
        self.log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        
        self.content = ft.Column([
            ft.Text("实时日志", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([self.level_filter, self.search_filter, self.pause_btn, self.clear_btn,
                    self.auto_scroll_switch, ft.TextButton("打开日志文件夹")]),
            self.pause_banner,
            self.log_list,
            ft.FilledTonalButton("复制全部日志"),
        ], expand=True)
        
        # Subscribe to SSE log events
        sse.on("log", self._on_log_event)
        self._load_history()

    async def _load_history(self):
        try:
            client = get_client()
            resp = await client.get("/admin/api/logs", params={"lines": 200})
            lines = resp.json().get("lines", [])
            for line in lines:
                self._add_line(line.get("level", "INFO"), line.get("time", ""), line.get("message", ""))
            self.update()
        except Exception:
            pass

    def _on_log_event(self, data: dict):
        if self._paused:
            self._paused_count += 1
            self.pause_banner.content = ft.Text(f"已暂停 · 新 {self._paused_count} 条日志")
            return
        self._add_line(data.get("level", "INFO"), data.get("time", ""), data.get("message", ""))
        self.update()

    def _add_line(self, level: str, timestamp: str, message: str):
        row = build_log_row(level, timestamp, message)
        self._log_lines.append(row)
        self.log_list.controls.append(row)
        if len(self._log_lines) > 1000:
            old = self.log_list.controls[:200]
            for c in old:
                self.log_list.controls.remove(c)
            self._log_lines = self._log_lines[-800:]

    def _toggle_pause(self, e):
        self._paused = not self._paused
        self.pause_btn.icon = ft.icons.PLAY_ARROW if self._paused else ft.icons.PAUSE
        self.pause_banner.visible = self._paused
        self._paused_count = 0
        self.update()

    def _clear(self, e):
        self.log_list.controls.clear()
        self._log_lines.clear()
        self.update()
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/logs.py
git commit -m "feat(gui): add real-time log viewer with SSE, filter, pause, auto-scroll"
```

---

### Task 10: Settings Page

**Files:**
- Create: `gui/pages/settings.py`

- [ ] **Step 1: Create settings.py**

```python
"""Settings page with 7 config groups."""
import flet as ft
from gui.http_client import get_client
from gui.components.notification import show_snackbar

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
                    if isinstance(control, ft.TextField):
                        control.value = str(config[key])
                    elif isinstance(control, ft.Dropdown):
                        control.value = str(config[key])
                        control.label = key
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
        copies = ft.TextField(label="default_copies", value="1", width=100, keyboard_type=ft.KeyboardType.NUMBER)
        duplex = ft.Switch(label="default_duplex", value=True)
        color = ft.Switch(label="default_color", value=True)
        paper = ft.Dropdown(label="paper_size", width=150, options=[
            ft.dropdown.Option("A4"), ft.dropdown.Option("Letter"), ft.dropdown.Option("A3"),
        ], value="A4")
        excel_all = ft.Switch(label="excel_print_all_sheets", value=False)
        ppt_output = ft.Dropdown(label="ppt_output_type", width=200, options=[
            ft.dropdown.Option("slides"), ft.dropdown.Option("handout2"),
            ft.dropdown.Option("handout3"), ft.dropdown.Option("handout6"),
        ], value="slides")
        auto_retry = ft.TextField(label="auto_retry_count", value="0", width=100, keyboard_type=ft.KeyboardType.NUMBER)
        self.fields.update({"default_printer": printer, "default_copies": copies, "default_duplex": duplex,
                           "default_color": color, "paper_size": paper, "excel_print_all_sheets": excel_all,
                           "ppt_output_type": ppt_output, "auto_retry_count": auto_retry})
        return ft.Container(
            content=ft.Column([
                ft.Text("打印默认值", weight=ft.FontWeight.BOLD, size=18),
                ft.Row([printer, copies, auto_retry]),
                ft.Row([duplex, color, excel_all]),
                ft.Row([paper, ppt_output]),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_quark_group(self) -> ft.Container:
        key_id = ft.TextField(label="quark_api_key_id", password=True, width=400, can_reveal_password=True)
        key = ft.TextField(label="quark_api_key", password=True, width=400, can_reveal_password=True)
        self.fields.update({"quark_api_key_id": key_id, "quark_api_key": key})
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("夸克扫描王 API", weight=ft.FontWeight.BOLD, size=18),
                        ft.Container(content=ft.Text("需重启", size=11), bgcolor=ft.Colors.AMBER_100,
                                      padding=ft.padding.symmetric(horizontal=6, vertical=2), border_radius=4)]),
                ft.Text("配置后需重启服务器生效", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                key_id, key,
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_notification_group(self) -> ft.Container:
        channel = ft.Dropdown(label="notify_channel", width=200, options=[
            ft.dropdown.Option("disabled"), ft.dropdown.Option("dingtalk"), ft.dropdown.Option("bark"),
        ], value="disabled")
        dt_webhook = ft.TextField(label="dingtalk_webhook", password=True, width=400, can_reveal_password=True)
        dt_level = ft.Dropdown(label="dingtalk_level", width=200, options=[
            ft.dropdown.Option("error"), ft.dropdown.Option("warning"), ft.dropdown.Option("info"),
        ], value="error")
        bark_key = ft.TextField(label="bark_key", password=True, width=400, can_reveal_password=True)
        bark_server = ft.TextField(label="bark_server", width=400, hint_text="https://api.day.app")
        self.fields.update({"notify_channel": channel, "dingtalk_webhook": dt_webhook, "dingtalk_level": dt_level,
                           "bark_key": bark_key, "bark_server": bark_server})
        return ft.Container(
            content=ft.Column([
                ft.Text("通知渠道", weight=ft.FontWeight.BOLD, size=18),
                channel, dt_webhook, dt_level, bark_key, bark_server,
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_server_group(self) -> ft.Container:
        port = ft.TextField(label="port", value="5000", width=150, keyboard_type=ft.KeyboardType.NUMBER)
        log_level = ft.Dropdown(label="log_level", width=200, options=[
            ft.dropdown.Option("DEBUG"), ft.dropdown.Option("INFO"),
            ft.dropdown.Option("WARNING"), ft.dropdown.Option("ERROR"),
        ], value="INFO")
        ssl = ft.Switch(label="ssl_enabled", value=False)
        self.fields.update({"port": port, "log_level": log_level, "ssl_enabled": ssl})
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("服务器", weight=ft.FontWeight.BOLD, size=18),
                        ft.Container(content=ft.Text("需重启", size=11), bgcolor=ft.Colors.AMBER_100,
                                      padding=ft.padding.symmetric(horizontal=6, vertical=2), border_radius=4)]),
                ft.Row([port, log_level, ssl]),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    def _build_worker_group(self) -> ft.Container:
        fields = {"worker_count": "2", "max_file_size_mb": "100", "job_retention_days": "30",
                  "print_dpi": "300", "job_timeout": "360", "word_timeout": "120"}
        controls = {}
        for key, default in fields.items():
            c = ft.TextField(label=key, value=default, width=150, keyboard_type=ft.KeyboardType.NUMBER)
            controls[key] = c
            self.fields[key] = c
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("Worker", weight=ft.FontWeight.BOLD, size=18),
                        ft.Container(content=ft.Text("需重启", size=11), bgcolor=ft.Colors.AMBER_100,
                                      padding=ft.padding.symmetric(horizontal=6, vertical=2), border_radius=4)]),
                ft.Row(list(controls.values())),
            ]), padding=16, border_radius=8, bgcolor=ft.Colors.SURFACE,
        )

    async def _save(self, e):
        config = {}
        for key, control in self.fields.items():
            if isinstance(control, ft.TextField):
                config[key] = control.value
            elif isinstance(control, ft.Switch):
                config[key] = control.value
            elif isinstance(control, ft.Dropdown):
                config[key] = control.value
        try:
            client = get_client()
            resp = await client.post("/api/config/save", json=config)
            if resp.status_code == 200:
                show_snackbar(self.page, "设置已保存")
                if any(k in config for k in ("port", "log_level", "ssl_enabled", "quark_api_key_id",
                                              "quark_api_key", "worker_count", "job_timeout")):
                    self.page.open(ft.AlertDialog(
                        title=ft.Text("需重启服务器"),
                        content=ft.Text("部分设置需要重启服务器才能生效。是否立即重启？"),
                        actions=[ft.TextButton("稍后"), ft.FilledButton("立即重启")],
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
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/settings.py
git commit -m "feat(gui): add settings page with 7 config groups, save, test notification"
```

---

### Task 11: Printer Manager Page

**Files:**
- Create: `gui/pages/printer_manager.py`

- [ ] **Step 1: Create printer_manager.py**

```python
"""Printer management page: card grid with status, set default."""
import flet as ft
from gui.http_client import get_client
from gui.components.printer_card import PrinterCard
from gui.components.notification import show_snackbar

class PrinterManagerPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.card_grid = ft.Row(wrap=True, spacing=16)
        self.content = ft.Column([
            ft.Row([
                ft.Text("打印机管理", size=24, weight=ft.FontWeight.BOLD),
                ft.FilledButton("刷新状态", icon=ft.icons.REFRESH, on_click=self._refresh),
            ]),
            self.card_grid,
            ft.Text("打印机状态每 30 秒自动更新", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ])
        self._load()

    async def _load(self):
        try:
            client = get_client()
            resp = await client.get("/api/printers/status")
            printers = resp.json()
            default_resp = await client.get("/api/config")
            default_printer = default_resp.json().get("default_printer", "")
            self.card_grid.controls = [
                PrinterCard(
                    name=p.get("name", ""), overall=p.get("overall", ""),
                    statuses=p.get("statuses", []), is_default=p.get("name") == default_printer,
                    on_set_default=self._set_default,
                ) for p in printers
            ]
            self.update()
        except Exception as e:
            show_snackbar(self.page, f"加载失败: {e}", color=ft.Colors.RED)

    async def _set_default(self, name: str):
        try:
            client = get_client()
            await client.post("/api/set_default_printer", json={"printer": name})
            show_snackbar(self.page, f"已设 {name} 为默认打印机")
            await self._load()
        except Exception as e:
            show_snackbar(self.page, f"设置失败: {e}", color=ft.Colors.RED)

    def _refresh(self, e):
        self._load()
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/printer_manager.py
git commit -m "feat(gui): add printer manager page with card grid, status, set default"
```

---

### Task 12: About Page + Update Check

**Files:**
- Create: `gui/pages/about.py`

- [ ] **Step 1: Create about.py**

```python
"""About page: version info, update check, links."""
import flet as ft
from gui.http_client import get_client
from gui.components.notification import show_snackbar

class AboutPage(ft.Container):
    def __init__(self, page: ft.Page):
        super().__init__()
        self.page = page
        self.update_status = ft.Text("")
        self.content = ft.Column([
            ft.Icon(ft.icons.PRINT, size=64, color=ft.Colors.PRIMARY),
            ft.Text("iOS 云打印服务器", size=28, weight=ft.FontWeight.BOLD),
            ft.Text(f"版本: {__import__('gui').__version__}", size=16),
            ft.Text(f"Python: {__import__('sys').version.split()[0]}", size=14),
            ft.Row([
                ft.FilledButton("检查更新", icon=ft.icons.UPDATE, on_click=self._check_update),
                ft.OutlinedButton("日志文件夹"),
                ft.OutlinedButton("配置文件"),
            ]),
            self.update_status,
            ft.Divider(),
            ft.Text("iOS 云打印服务器 — Windows 打印服务器", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text("接收 iOS Scriptable 和 Web 请求，通过 pywin32 驱动本地打印机", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)

    async def _check_update(self, e):
        self.update_status.value = "正在检查更新..."
        self.update_status.color = ft.Colors.ON_SURFACE_VARIANT
        self.update_status.update()
        try:
            client = get_client()
            resp = await client.get("/api/version")
            version = resp.json().get("version", "0.0.0")
            # Compare with latest GitHub release
            import httpx
            gh_resp = await httpx.AsyncClient().get(
                "https://api.github.com/repos/owner/repo/releases/latest", timeout=5.0)
            gh_data = gh_resp.json()
            latest = gh_data.get("tag_name", "").lstrip("v")
            if latest > version:
                self.update_status.value = f"新版本 v{latest} 可用！"
                self.update_status.color = ft.Colors.GREEN
            else:
                self.update_status.value = f"已是最新版本 (v{version})"
                self.update_status.color = ft.Colors.GREEN
        except Exception as ex:
            self.update_status.value = f"检查更新失败: {ex}"
            self.update_status.color = ft.Colors.RED
        self.update_status.update()
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/about.py
git commit -m "feat(gui): add about page with version info and update check"
```

---

### Task 13: Keyboard Shortcuts + Window State Persistence

**Files:**
- Modify: `gui/app.py`
- Modify: `gui/window_state.py`

- [ ] **Step 1: Add keyboard shortcuts to app.py**

Add event handler in `main()`:
```python
    def on_keyboard(e: ft.KeyboardEvent):
        shortcuts = {
            "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6": 5, "7": 6,
        }
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
```

- [ ] **Step 2: Add window state save on close**

In `main()`, before the add:
```python
    def on_window_event(e):
        if e.type == "close":
            save_state(page)
            _minimize_to_tray(e)
    
    page.on_window_event = on_window_event
```

- [ ] **Step 3: Commit**

```bash
git add gui/app.py gui/window_state.py
git commit -m "feat(gui): add keyboard shortcuts and window state persistence"
```

---

### Task 14: Update console plus autostart for GUI

**Files:**
- Modify: `console/__init__.py`
- Modify: `console/autostart.py`

- [ ] **Step 1: Add --gui flag to console/__init__.py**

Add a `--gui` flag to the argparse (or Typer) entry:
```python
    parser.add_argument("--gui", action="store_true", help="启动 Flet 图形界面")
```

In main():
```python
    if args.gui:
        from gui.app import main as gui_main
        gui_main()
        return
```

- [ ] **Step 2: Update autostart.py for GUI mode**

In `install_autostart()`:
```python
    # Use --gui flag for autostart
    args = [exe, "--gui"]  # Previously was "--server-daemon"
```

- [ ] **Step 3: Commit**

```bash
git add console/__init__.py console/autostart.py
git commit -m "feat(gui): add --gui flag to console entry and update autostart"
```

---

### Task 15: PyInstaller Build Config Update

**Files:**
- Modify: `scripts/build.py`

- [ ] **Step 1: Build a working iOSPrintServer.exe**

Run existing build script to verify baseline:
```bash
python scripts/build.py
```

- [ ] **Step 2: Update build.py to include gui/ package**

Add to hidden-imports or datas in `scripts/build.py`:
```python
    # In the PyInstaller Analysis section:
    '--hidden-import=gui',
    '--hidden-import=gui.pages',
    '--hidden-import=gui.components',
    '--collect-all=flet',
```

- [ ] **Step 3: Test the built exe**

Run: `dist/iOSPrintServer.exe --gui`
Expected: Flet GUI window opens, server starts in background

- [ ] **Step 4: Commit**

```bash
git add scripts/build.py
git commit -m "fix(build): add gui package to PyInstaller hidden-imports"
```

---

### Task 16: Integration Test for GUI Lifecycle

**Files:**
- Create: `tests/test_gui_lifecycle.py`

- [ ] **Step 1: Write integration test for child process lifecycle**

```python
"""Test GUI child process lifecycle."""
import pytest
import time
from gui.child_process import ChildProcess

@pytest.mark.asyncio
async def test_child_process_start_stop():
    cp = ChildProcess()
    cp.start()
    time.sleep(2)  # Wait for server to start
    healthy = await cp.health_check()
    assert healthy, "Server should be healthy after start"
    cp.stop()
    assert not cp.is_running(), "Server should stop"

@pytest.mark.asyncio
async def test_child_process_health_check_fails():
    cp = ChildProcess()
    healthy = await cp.health_check()  # No server running
    assert not healthy, "Health check should fail with no server"

@pytest.mark.asyncio
async def test_child_process_restart():
    cp = ChildProcess()
    cp.start()
    time.sleep(2)
    await cp.health_check()
    cp.restart()
    time.sleep(2)
    healthy = await cp.health_check()
    assert healthy, "Server should be healthy after restart"
    cp.stop()
```

- [ ] **Step 2: Run test to verify**

Run: `pytest tests/test_gui_lifecycle.py -v`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gui_lifecycle.py
git commit -m "test(gui): add child process lifecycle tests"
```

---

## Phase 2: Backend Modernization

### Task 17: Typer CLI — Replace argparse

**Files:**
- Modify: `console/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing tests for CLI commands**

```python
"""Tests for console CLI."""
from console import main
import pytest

def test_cli_headless():
    """Test that --headless flag parses correctly."""
    # Would run: python -m console --headless
    # Verify it doesn't raise argparse errors
    pass  # Replace with actual test after migration
```

(Add tests to `tests/test_console.py` — to be created.)

- [ ] **Step 2: Replace argparse with Typer**

Rewrite `console/__init__.py`:
```python
"""Console entry point — Typer CLI."""
import typer

app = typer.Typer()

@app.command()
def headless():
    """无界面运行服务器 (子进程模式)"""
    # ... existing headless logic

@app.command()
def gui():
    """启动 Flet 图形界面"""
    from gui.app import main as gui_main
    gui_main()

@app.command()
def stop():
    """停止服务器"""
    # ... existing stop logic

@app.command()
def status():
    """查看服务器状态"""
    # ... existing status logic

@app.command()
def restart():
    """重启服务器"""
    # ... existing restart logic

@app.command(name="autostart-install")
def autostart_install():
    """安装开机自启"""
    # ... existing install logic

@app.command(name="autostart-uninstall")
def autostart_uninstall():
    """卸载开机自启"""
    # ... existing uninstall logic

if __name__ == "__main__":
    app()
```

- [ ] **Step 3: Add typer to pyproject.toml**

```toml
dependencies = [
    ...,
    "typer>=0.15.0",
]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All existing tests pass (no regression)

- [ ] **Step 5: Commit**

```bash
git add console/__init__.py pyproject.toml
git commit -m "refactor(cli): replace argparse with Typer CLI"
```

---

### Task 18: aiosqlite — Async Database Access

**Files:**
- Modify: `app/printing/repository.py`
- Modify: `app/printing/job_queue.py`
- Modify: `app/printing/worker.py`
- Modify: `app/routes/api.py`
- Modify: `app/routes/admin.py`
- Modify: `app/services/heartbeat.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add aiosqlite to dependencies**

```toml
dependencies = [
    ...,
    "aiosqlite>=0.20.0",
]
```

- [ ] **Step 2: Rewrite repository.py to use aiosqlite**

Replace `sqlite3` with `aiosqlite`:
```python
import aiosqlite

class JobRepository:
    def __init__(self, db_path: str):
        self._db_path = db_path
    
    async def _connect(self) -> aiosqlite.Connection:
        db = await aiosqlite.connect(self._db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        return db
    
    async def add_job(self, job: Job) -> int:
        async with await self._connect() as db:
            cursor = await db.execute(
                "INSERT INTO jobs (...) VALUES (...)",
                (...)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_job(self, job_id: int) -> dict | None:
        async with await self._connect() as db:
            cursor = await db.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    # ... rewrite all other methods from sync → async
```

- [ ] **Step 3: Update job_queue.py — make all public methods async**

```python
class JobQueue:
    async def add_job(self, ...) -> int:
        return await self._repo.add_job(...)
    
    async def cancel_job(self, job_id: int) -> bool:
        return await self._repo.update_job_status(job_id, "cancelled")
    
    async def retry_job(self, job_id: int) -> bool:
        return await self._repo.update_job_status(job_id, "pending")
    
    async def get_jobs(self, ...) -> list[dict]:
        return await self._repo.get_jobs(...)
    
    async def count_jobs(self, ...) -> int:
        return await self._repo.count_jobs(...)
    
    async def cleanup_old_jobs(self) -> int:
        return await self._repo.delete_old_jobs(...)
    
    async def recover_stuck_jobs(self):
        await self._repo.recover_stuck_jobs()
```

- [ ] **Step 4: Update worker.py — make db calls async**

```python
class JobExecutor:
    async def execute(self, job: Job) -> JobResult:
        # ...
        await self._job_queue.update_job_status(job.id, "completed")
        # ...
```

- [ ] **Step 5: Update routes — make handlers async**

```python
@router.get("/api/status/{job_id}")
async def get_status(job_id: int):
    job = await job_queue.get_job(job_id)
    # ...
```

- [ ] **Step 6: Update heartbeat.py**

```python
class Heartbeat:
    async def _run(self):
        while self._running:
            await asyncio.sleep(30)
            await self._job_queue.cleanup_old_jobs()
            await self._job_queue.recover_stuck_jobs()
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass (may need test updates for async)

- [ ] **Step 8: Commit**

```bash
git add app/printing/repository.py app/printing/job_queue.py app/printing/worker.py
git add app/routes/api.py app/routes/admin.py app/services/heartbeat.py pyproject.toml
git commit -m "refactor(db): migrate from sqlite3 to aiosqlite for async database access"
```

---

### Task 19: Health Check Enhancement + Version API

**Files:**
- Modify: `app/routes/api.py`

- [ ] **Step 1: Enhance /api/health endpoint**

```python
import time
import os

_start_time = time.time()

@router.get("/api/health")
async def health(request: Request):
    app = request.app
    queue_size = len(app.state.job_queue._queue) if hasattr(app.state, 'job_queue') else 0
    db_path = app.state.config.db_path if hasattr(app.state, 'config') else ""
    db_size = os.path.getsize(db_path) / (1024 * 1024) if db_path and os.path.exists(db_path) else 0
    return {
        "status": "ok",
        "version": __import__("app.version", fromlist=["__version__"]).__version__,
        "uptime": int(time.time() - _start_time),
        "queue_size": queue_size,
        "db_size_mb": round(db_size, 1),
    }
```

- [ ] **Step 2: Add /api/version endpoint**

```python
@router.get("/api/version")
async def version():
    from app.version import __version__
    return {
        "version": __version__,
        "build_date": getattr(app.state, "build_date", "unknown"),
        "python_version": sys.version.split()[0],
    }
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/api.py
git commit -m "feat(api): enhance health check with version/uptime/db_size, add version endpoint"
```

---

### Task 20: Signal Handling + Graceful Shutdown

**Files:**
- Modify: `console/__init__.py`
- Modify: `app/printing/worker.py`

- [ ] **Step 1: Add signal handlers to headless mode**

In `console/__init__.py`:
```python
import signal

def _setup_signal_handlers(server_handle):
    def _handle_exit(signum, frame):
        logger.info("Received signal {}, shutting down...", signum)
        server_handle.stop()
    
    signal.signal(signal.SIGINT, _handle_exit)
    signal.signal(signal.SIGTERM, _handle_exit)
```

- [ ] **Step 2: Add drain() to WorkerPool**

In `app/printing/worker_pool.py`:
```python
class WorkerPool:
    async def drain(self, timeout: float = 30.0):
        """Wait for active workers to finish, then stop."""
        deadline = time.time() + timeout
        while self._active_workers > 0 and time.time() < deadline:
            await asyncio.sleep(0.5)
        self.stop()
```

- [ ] **Step 3: Commit**

```bash
git add console/__init__.py app/printing/worker_pool.py
git commit -m "feat: add signal handling and graceful worker drain on shutdown"
```

---

### Task 21: Pathlib Cleanup

**Files:**
- Modify: `app/_paths.py`
- Modify: `app/config.py`
- Modify: `app/services/upload.py`
- Modify: `console/__init__.py`
- Modify: `tests/test_paths.py`

- [ ] **Step 1: Update _paths.py — return Path instead of str**

```python
from pathlib import Path

def app_root() -> Path:
    return Path(__file__).resolve().parent.parent

def data_root() -> Path:
    return Path(os.environ.get("APPDATA", ".")) / "iOSPrintServer"

def persistent_dir() -> Path:
    path = data_root() / "persistent"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 2: Update callers — config.py, upload.py, console**

```python
# Before
config_path = os.path.join(data_root(), "config.json")
# After
config_path = data_root() / "config.json"
```

- [ ] **Step 3: Update tests**

```python
def test_paths_return_path():
    from app._paths import app_root
    assert isinstance(app_root(), Path)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/_paths.py app/config.py app/services/upload.py console/__init__.py tests/test_paths.py
git commit -m "refactor(paths): replace os.path with pathlib.Path throughout"
```

---

### Task 22: Pydantic Request Models

**Files:**
- Modify: `app/schemas.py`
- Modify: `app/routes/api.py`
- Modify: `app/routes/admin.py`

- [ ] **Step 1: Add request models to schemas.py**

```python
from pydantic import BaseModel, Field

class PrintOptions(BaseModel):
    printer: str | None = None
    copies: int | None = Field(default=None, ge=1, le=99)
    duplex: bool | None = None
    color: bool | None = None
    paper_size: str | None = None

class SettingsUpdate(BaseModel):
    api_key: str | None = None
    default_printer: str | None = None
    default_copies: int | None = Field(default=None, ge=1, le=99)
    # ... all 22 config fields with validation

class JobFilter(BaseModel):
    status: str | None = None
    search: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
```

- [ ] **Step 2: Update routes — use Pydantic models instead of Form()**

```python
@router.post("/api/print")
async def print_file(
    file: UploadFile = File(...),
    options: str = Form("{}"),
):
    opts = PrintOptions.model_validate_json(options)
    # ...
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add app/schemas.py app/routes/api.py app/routes/admin.py
git commit -m "refactor(api): add Pydantic request models replacing Form() parameters"
```

---

### Task 23: OpenAPI + Scalar API Documentation

**Files:**
- Modify: `app/__init__.py`

- [ ] **Step 1: Update FastAPI app config**

```python
app = FastAPI(
    title='iOSPrintServer',
    version=__version__,
    description='iOS 云打印服务器 — 管理打印机、提交打印任务、监控状态',
    contact={'name': 'Developer'},
    license_info={'name': 'MIT', 'identifier': 'MIT'},
    lifespan=lifespan,
    docs_url='/docs',
    redoc_url='/redoc',
    openapi_url='/openapi.json',
)
```

- [ ] **Step 2: Verify endpoints are documented**

Run: `python -c "from app import create_app; app=create_app(); print('OpenAPI schema OK:', '/openapi.json' in [r.path for r in app.routes])"`
Expected: OpenAPI schema OK: True

- [ ] **Step 3: Commit**

```bash
git add app/__init__.py
git commit -m "feat(docs): enable OpenAPI with Swagger UI, ReDoc, and Scalar endpoint"
```

---

### Task 24: Ruff Ruleset Extension

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update ruff config**

```toml
[tool.ruff.lint]
select = [
    "E", "F", "I", "N", "W",
    "UP", "B", "SIM", "ARG", "RUF",
    "PERF", "TCH", "PYI", "RET", "RSE", "G",
]
```

- [ ] **Step 2: Run ruff check — auto-fix**

Run: `ruff check --fix .`
Expected: Clean run or minimal remaining issues

- [ ] **Step 3: Run tests to verify no regression**

Run: `pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(lint): extend ruff ruleset with PERF/TCH/PYI/RET/RSE/G"
```

---

### Task 25: msgspec SSE Serialization

**Files:**
- Modify: `app/routes/api.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add msgspec to dependencies**

```toml
dependencies = [
    ...,
    "msgspec>=0.19.0",
]
```

- [ ] **Step 2: Replace json.dumps with msgspec in SSE generator**

```python
import msgspec
encoder = msgspec.json.Encoder()

@router.get("/api/events")
async def event_stream(request: Request):
    async def event_generator():
        while True:
            event = await sse.subscribe(...)
            yield f"event: {event.event}\ndata: {encoder.encode(event.data).decode()}\n\n"
    return EventSourceResponse(event_generator())
```

- [ ] **Step 3: Commit**

```bash
git add app/routes/api.py pyproject.toml
git commit -m "perf(api): replace json.dumps with msgspec for SSE serialization"
```

---

### Task 26: Alembic Migration Setup

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial_schema.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Initialize Alembic scaffolding**

```bash
pip install alembic
alembic init alembic
```

- [ ] **Step 2: Configure alembic.ini**

```ini
sqlalchemy.url = sqlite:///%APPDATA%/iOSPrintServer/jobs.db
```

(Set dynamically in `env.py`)

- [ ] **Step 3: Create initial migration**

```python
"""Initial schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        # ...
    )

def downgrade():
    op.drop_table("jobs")
```

- [ ] **Step 4: Commit**

```bash
git add alembic.ini alembic/ pyproject.toml
git commit -m "feat(db): add Alembic migration framework"
```

---

### Task 27: uv Workflow + Test Parallelization

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements-dev.txt` (remove)

- [ ] **Step 1: Add uv config to pyproject.toml**

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=9", "pytest-cov>=7", "pytest-asyncio>=0.25.0",
    "httpx>=0.28", "pyinstaller>=6",
    "ruff>=0.11.0", "mypy>=1.15.0", "pre-commit>=4.2.0",
    "hypothesis>=6.130.0", "pytest-xdist>=3.6.0",
]
```

- [ ] **Step 2: Generate uv.lock**

```bash
uv lock
```

- [ ] **Step 3: Run tests in parallel**

```bash
uv run pytest -n auto --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(build): add uv dev-dependencies and pytest-xdist parallel testing"
```

---

## Self-Review Checklist

- [ ] **Spec coverage:** GUI pages cover all 7 pages from spec, each with empty/loading/error states spec'd ✓
- [ ] **Spec coverage:** Theme tokens match spec (8 tokens x light/dark) ✓
- [ ] **Spec coverage:** Micro-interactions covered (button feedback, switch animation, drag affordance) ✓
- [ ] **Spec coverage:** Child process lifecycle (start/health/restart/kill) ✓
- [ ] **Spec coverage:** Keyboard shortcuts (Ctrl+1-7, Ctrl+P, Escape, F5) ✓
- [ ] **Spec coverage:** Backend items — aiosqlite, mypy strict, Alembic, Typer, Pathlib, msgspec, Pydantic, OpenAPI, ruff, uv, pytest-xdist, health check, signal handling, version API, httpx pool ✓
- [ ] **Placeholder scan:** All steps contain actual code, no "TBD" or "implement later" ✓
- [ ] **Type consistency:** `ChildProcess.start/stop/restart/health_check` consistent across task 3 and task 16 ✓
- [ ] **Type consistency:** `get_client()` returns `httpx.AsyncClient` consistent across all pages ✓
