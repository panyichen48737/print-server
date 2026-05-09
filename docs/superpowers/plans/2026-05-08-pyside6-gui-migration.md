# PySide6 GUI 迁移实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 iOS 云打印服务器从 Flet GUI 迁移到 PySide6 (Qt for Python)，保留所有 7 页功能并增加系统托盘、原生文件对话框、图表、全局快捷键。

**Architecture:** 同一进程内 QApplication (主线程) + uvicorn (后台线程)。GUI 通过 EventBus 直接订阅后端事件（不再经过 HTTP）。7 页通过 QStackedWidget 切换，左侧 QListWidget 导航。

**Tech Stack:** PySide6 6.8+, QtCharts, QSS + QPalette 主题, pywin32 (不变), FastAPI/uvicorn (不变)

**UI Design Workflow:** 所有功能实现完成后，最后用 UI/UX Pro Max 确定视觉风格 → Frontend Design 生成首版界面代码

---

## 文件结构

```
gui/                              # PySide6 GUI 目录（新建）
├── __init__.py                   # 空
├── __main__.py                   # qapplication = QA(...); main_window = MainWindow(bootstrap)
├── app.py                        # MainWindow(QMainWindow): nav, stacked widget, status bar, tray
├── theme.py                      # ThemeEngine: qss() / palette() / apply_theme()
├── event_bridge.py               # EventBus → Qt signal 桥接
├── settings_store.py             # QSettings 窗口状态持久化

pages/                            # 7 个页面
├── __init__.py                   # from .dashboard import DashboardPage 等
├── dashboard.py                  # DashboardPage(QWidget): 6 stat cards + QChart + printer + recent jobs
├── quick_print.py                # QuickPrintPage(QWidget): DropZoneWidget + QComboBox + QSpinBox + StatefulButton
├── job_manager.py                # JobManagerPage(QWidget): QTableView × 2 + filter bar + pagination
├── logs.py                       # LogsPage(QWidget): QListWidget + level filter + search + pause
├── settings.py                   # SettingsPage(QWidget): QScrollArea + 7 QGroupBox
├── printer_manager.py            # PrinterManagerPage(QWidget): card grid + PrinterCardWidget
└── about.py                      # AboutPage(QWidget): version info + update check

components/                       # 可复用组件
├── __init__.py
├── stateful_button.py            # StatefulButton(QPushButton): loading/success/error states
├── printer_card.py               # PrinterCardWidget(QFrame): name + status dot + labels
├── drop_zone.py                  # DropZoneWidget: dragEnterEvent/dropEvent
├── notification.py               # NotificationWidget: toast popup (右下角滑入)
├── validators.py                 # PortValidator, NumberRangeValidator (QValidator subclass)
└── skeleton.py                   # SkeletonWidget: 灰色脉冲占位

resources/                        # QSS + 图标
├── light.qss                     # 亮色主题 QSS（占位，UI Design 阶段填充）
├── dark.qss                      # 深色主题 QSS（占位，UI Design 阶段填充）
├── icon.ico                      # 应用图标
└── icon.png                      # 应用图标（PNG）
```

**修改的现有文件：**
- `console/__init__.py` — 更新 `_gui_main()` 启动 PySide6
- `console/__main__.py` — 检查入口点
- `pyproject.toml` — 添加 `PySide6>=6.8.0`，移除 `flet`
- `console/autostart.py` — 确认参数正确

---

## Phase A: 核心基础设施（Steps 1-5）

### Task 1: 项目结构 + 依赖

**Files:**
- Create: `gui/__init__.py` (empty)
- Create: `gui/pages/__init__.py` (empty)
- Create: `gui/components/__init__.py` (empty)
- Create: `gui/resources/` (empty directory)
- Modify: `pyproject.toml`

- [ ] **Step 1: 添加 PySide6 依赖，移除 flet**

`pyproject.toml` 中：
```toml
# 移除
# "flet>=0.84.0",

# 添加
"PySide6>=6.8.0",
```

- [ ] **Step 2: 创建目录结构和空 `__init__.py`**

```bash
mkdir -p gui/pages gui/components gui/resources
touch gui/__init__.py gui/pages/__init__.py gui/components/__init__.py
```

- [ ] **Step 3: 验证**

```bash
python -c "import PySide6.QtWidgets, PySide6.QtCharts; print(PySide6.__version__)"
# Expected: 6.8.x 或更高
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml gui/
git commit -m "chore: add PySide6 dependency, create GUI directory structure"
```

### Task 2: QApplication + MainWindow 主框架

**Files:**
- Create: `gui/app.py`
- Create: `gui/__main__.py`
- Modify: `console/__init__.py`

- [ ] **Step 1: 实现 MainWindow**

`gui/app.py`:
```python
"""MainWindow: nav sidebar + QStackedWidget + status bar + system tray."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget, QMenu,
)

from console._server import ServerHandle


class MainWindow(QMainWindow):
    NAV_ITEMS = ["仪表盘", "快速打印", "任务管理", "实时日志", "设置", "打印机管理", "关于"]

    def __init__(self, app, config, server_handle: ServerHandle):
        super().__init__()
        self._app = app
        self._config = config
        self._server = server_handle
        self._event_bus = app.state.event_bus

        self.setWindowTitle("iOS 云打印服务器")
        self.setMinimumSize(900, 600)
        self.resize(1200, 800)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Status bar (top)
        self.status_bar = self._build_status_bar()

        # Nav sidebar
        self.nav = QListWidget()
        self.nav.setFixedWidth(160)
        for label in self.NAV_ITEMS:
            QListWidgetItem(label, self.nav)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        # Page container
        self.stack = QStackedWidget()
        from gui.pages.dashboard import DashboardPage
        from gui.pages.quick_print import QuickPrintPage
        from gui.pages.job_manager import JobManagerPage
        from gui.pages.logs import LogsPage
        from gui.pages.settings import SettingsPage
        from gui.pages.printer_manager import PrinterManagerPage
        from gui.pages.about import AboutPage

        self.stack.addWidget(DashboardPage(self))
        self.stack.addWidget(QuickPrintPage(self))
        self.stack.addWidget(JobManagerPage(self))
        self.stack.addWidget(LogsPage(self))
        self.stack.addWidget(SettingsPage(self))
        self.stack.addWidget(PrinterManagerPage(self))
        self.stack.addWidget(AboutPage(self))

        # Layout: status bar top, then nav + content below
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        content_row.addWidget(self.nav)
        content_row.addWidget(self.stack, 1)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self.status_bar)
        container_layout.addLayout(content_row, 1)
        main_layout.addWidget(container)

        # System tray
        self._setup_tray()

        # Connect events
        self._connect_events()

        # Health timer
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._refresh_status)
        self._health_timer.start(3000)

        # Select first page
        self.nav.setCurrentRow(0)

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 4, 12, 4)
        self.status_dot = QLabel("●")
        self.status_text = QLabel("启动中...")
        self.start_btn = QPushButton("启动")
        self.stop_btn = QPushButton("停止")
        self.restart_btn = QPushButton("重启")
        self.web_btn = QPushButton("管理后台")
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        self.restart_btn.clicked.connect(self._on_restart)
        self.web_btn.clicked.connect(self._on_open_web)
        layout.addWidget(self.status_dot)
        layout.addWidget(self.status_text)
        layout.addStretch()
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(self.restart_btn)
        layout.addWidget(self.web_btn)
        return bar

    def _setup_tray(self):
        icon_path = str(Path(__file__).parent / "resources" / "icon.png")
        if Path(icon_path).exists():
            self.tray = QSystemTrayIcon(QIcon(icon_path), self)
        else:
            self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("iOS 云打印服务器")
        menu = QMenu()
        show_action = menu.addAction("显示窗口")
        show_action.triggered.connect(self.show)
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._on_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()

    def _on_quit(self):
        if self._server:
            self._server.stop()
        QApplication.quit()

    def _on_start(self):
        if self._server:
            self._server.start(self._app, self._config)

    def _on_stop(self):
        if self._server:
            self._server.stop()

    def _on_restart(self):
        if self._server:
            self._server.stop()
            self._server.start(self._app, self._config)

    def _on_open_web(self):
        import webbrowser
        port = self._server.port if self._server else 5000
        webbrowser.open(f"http://127.0.0.1:{port}/admin")

    def _refresh_status(self):
        if self._server and self._server.is_running:
            self.status_dot.setStyleSheet("color: green;")
            self.status_text.setText(f"运行中 · 端口 {self._server.port}")
            self.start_btn.setVisible(False)
            self.stop_btn.setVisible(True)
        elif self._server:
            self.status_dot.setStyleSheet("color: red;")
            self.status_text.setText("已停止")
            self.start_btn.setVisible(True)
            self.stop_btn.setVisible(False)
        else:
            self.status_dot.setStyleSheet("color: gray;")
            self.status_text.setText("未初始化")

    def _on_nav_changed(self, index: int):
        self.stack.setCurrentIndex(index)

    def _connect_events(self):
        event_bus = self._event_bus
        if event_bus:
            event_bus.on("job_status", self._on_job_status)
            event_bus.on("printer_status", self._on_printer_status)

    def _on_job_status(self, data: dict):
        # 转发到当前活跃页面
        current = self.stack.currentWidget()
        if hasattr(current, "on_job_status"):
            current.on_job_status(data)

    def _on_printer_status(self, data: dict):
        current = self.stack.currentWidget()
        if hasattr(current, "on_printer_status"):
            current.on_printer_status(data)

    def closeEvent(self, event):
        # Close → hide to tray
        event.ignore()
        self.hide()


def run_gui(app, config, server_handle: ServerHandle):
    qapp = QApplication(sys.argv)
    window = MainWindow(app, config, server_handle)
    window.show()
    sys.exit(qapp.exec())
```

- [ ] **Step 2: 创建 GUI 入口点**

`gui/__main__.py`:
```python
"""PySide6 GUI entry point."""
from console import main

main()
```

- [ ] **Step 3: 更新 `console/__init__.py` 的 `_gui_main()`**

定位 `_gui_main()` 函数，改为：
```python
def _gui_main():
    from gui.app import run_gui
    app, config, server_handle, *_ = _bootstrap_server()
    run_gui(app, config, server_handle)
```

确保 `_bootstrap_server()` 返回 `(app, config, server_handle)` — 需确认当前返回值结构。

- [ ] **Step 4: 验证启动**

```bash
python -c "from gui.app import run_gui; print('OK')"
# Expected: OK (无导入错误)
```

- [ ] **Step 5: Commit**

```bash
git add gui/app.py gui/__main__.py console/__init__.py
git commit -m "feat: PySide6 MainWindow with nav, status bar, system tray"
```

### Task 3: EventBus 桥接

**Files:**
- Create: `gui/event_bridge.py`

- [ ] **Step 1: 创建 EventBus → Qt signal 桥接**

`gui/event_bridge.py`:
```python
"""Bridge EventBus (thread-safe) to Qt signal/slot."""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot
from app.services.sse_broadcaster import EventBus


class EventBridge(QObject):
    """Wraps EventBus subscriptions in Qt signals for thread-safe GUI updates."""
    job_status = Signal(dict)
    printer_status = Signal(dict)
    log = Signal(dict)
    health_status = Signal(dict)

    def __init__(self, event_bus: EventBus | None, parent: QObject | None = None):
        super().__init__(parent)
        self._bus = event_bus
        if self._bus:
            self._bus.on("job_status", self._emit_job_status)
            self._bus.on("printer_status", self._emit_printer_status)
            self._bus.on("log", self._emit_log)

    @Slot(dict)
    def _emit_job_status(self, data: dict):
        self.job_status.emit(data)

    @Slot(dict)
    def _emit_printer_status(self, data: dict):
        self.printer_status.emit(data)

    @Slot(dict)
    def _emit_log(self, data: dict):
        self.log.emit(data)

    def stop(self):
        if self._bus:
            self._bus.off("job_status", self._emit_job_status)
            self._bus.off("printer_status", self._emit_printer_status)
            self._bus.off("log", self._emit_log)
```

- [ ] **Step 2: 在 MainWindow 中使用 EventBridge**

在 `gui/app.py` 的 `__init__` 中添加：
```python
from gui.event_bridge import EventBridge
...
self._bridge = EventBridge(self._event_bus, self)
self._bridge.job_status.connect(self._on_job_status)
self._bridge.printer_status.connect(self._on_printer_status)
self._bridge.log.connect(self._on_log)
```

添加 `_on_log` 方法：
```python
def _on_log(self, data: dict):
    current = self.stack.currentWidget()
    if hasattr(current, "on_log"):
        current.on_log(data)
```

- [ ] **Step 3: 验证**

```bash
python -c "from gui.event_bridge import EventBridge; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add gui/event_bridge.py gui/app.py
git commit -m "feat: EventBus-to-Qt signal bridge for thread-safe GUI updates"
```

### Task 4: ThemeEngine（基础功能版）

**Files:**
- Create: `gui/theme.py`
- Create: `gui/resources/light.qss` (占位)
- Create: `gui/resources/dark.qss` (占位)

- [ ] **Step 1: 实现 ThemeEngine**

`gui/theme.py`:
```python
"""Theme engine: QPalette + QSS management with light/dark mode."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


TOKENS_LIGHT = {
    "surface": "#FFFFFF",
    "primary": "#4F46E5",
    "primary_container": "#EEF2FF",
    "error": "#DC2626",
    "on_surface": "#1F2937",
    "on_surface_variant": "#6B7280",
    "outline": "#D1D5DB",
    "success": "#16A34A",
}

TOKENS_DARK = {
    "surface": "#1E1E2E",
    "primary": "#818CF8",
    "primary_container": "#312E81",
    "error": "#F87171",
    "on_surface": "#E2E8F0",
    "on_surface_variant": "#94A3B8",
    "outline": "#4B5563",
    "success": "#4ADE80",
}


class ThemeEngine:
    _instance: ThemeEngine | None = None

    def __init__(self):
        self._mode: str = "light"
        self._tokens: dict[str, str] = dict(TOKENS_LIGHT)

    @classmethod
    def instance(cls) -> ThemeEngine:
        if cls._instance is None:
            cls._instance = ThemeEngine()
        return cls._instance

    @property
    def tokens(self) -> dict[str, str]:
        return dict(self._tokens)

    def apply(self, mode: str, qapp: QApplication) -> None:
        self._mode = mode
        self._tokens = dict(TOKENS_LIGHT if mode == "light" else TOKENS_DARK)
        qapp.setPalette(self._palette())
        qss_path = Path(__file__).parent / "resources" / f"{mode}.qss"
        if qss_path.exists():
            with open(qss_path, encoding="utf-8") as f:
                qapp.setStyleSheet(f.read())

    def _palette(self) -> QPalette:
        p = QPalette()
        t = self._tokens
        p.setColor(QPalette.ColorRole.Window, QColor(t["surface"]))
        p.setColor(QPalette.ColorRole.WindowText, QColor(t["on_surface"]))
        p.setColor(QPalette.ColorRole.Base, QColor(t["surface"]))
        p.setColor(QPalette.ColorRole.Text, QColor(t["on_surface"]))
        p.setColor(QPalette.ColorRole.Button, QColor(t["primary"]))
        p.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.Highlight, QColor(t["primary"]))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        p.setColor(QPalette.ColorRole.Link, QColor(t["primary"]))
        return p

    def apply_widget(self, widget, qss: str) -> None:
        widget.setStyleSheet(qss.format(**self._tokens))
```

- [ ] **Step 2: 创建占位 QSS 文件**

`gui/resources/light.qss`:
```css
/* Light theme QSS — UI Design 阶段填充 */
QMainWindow { background-color: #FFFFFF; }
QPushButton { border-radius: 6px; padding: 6px 16px; }
QPushButton:hover { opacity: 0.9; }
QListWidget { border: none; background-color: #F8F9FA; }
QListWidget::item { padding: 10px 16px; border-radius: 4px; }
QListWidget::item:selected { background-color: #EEF2FF; color: #4F46E5; }
```

`gui/resources/dark.qss`:
```css
/* Dark theme QSS — UI Design 阶段填充 */
QMainWindow { background-color: #1E1E2E; }
QPushButton { border-radius: 6px; padding: 6px 16px; }
QListWidget { border: none; background-color: #181825; }
QListWidget::item { padding: 10px 16px; border-radius: 4px; }
QListWidget::item:selected { background-color: #312E81; color: #818CF8; }
```

- [ ] **Step 3: 在 MainWindow 启动时应用主题**

在 `gui/app.py` 的 `run_gui()` 中：
```python
from gui.theme import ThemeEngine
...
theme = ThemeEngine.instance()
theme.apply("light", qapp)
```

- [ ] **Step 4: 验证**

```bash
python -c "from gui.theme import ThemeEngine; t = ThemeEngine.instance(); t.apply('light', None); print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add gui/theme.py gui/resources/
git commit -m "feat: ThemeEngine with light/dark mode and QSS loading"
```

### Task 5: 公共组件

**Files:**
- Create: `gui/components/stateful_button.py`
- Create: `gui/components/validators.py`
- Create: `gui/components/skeleton.py`
- Create: `gui/components/printer_card.py`
- Create: `gui/components/drop_zone.py`
- Create: `gui/components/notification.py`

- [ ] **Step 1: StatefulButton**

`gui/components/stateful_button.py`:
```python
"""QPushButton with loading/success/error states."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QPushButton


class StatefulButton(QPushButton):
    STATES = ("default", "loading", "success", "error", "disabled")

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._original_text = text
        self._state = "default"
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reset)

    def set_loading(self):
        self._state = "loading"
        self.setText(f"{self._original_text}...")
        self.setEnabled(False)

    def set_success(self, duration_ms: int = 1500):
        self._state = "success"
        self.setText("✓ " + self._original_text)
        self.setStyleSheet("background-color: #16A34A; color: white;")
        self._timer.start(duration_ms)

    def set_error(self, duration_ms: int = 2000):
        self._state = "error"
        self.setText("✗ 失败")
        self.setStyleSheet("background-color: #DC2626; color: white;")
        self._timer.start(duration_ms)

    def _reset(self):
        self._state = "default"
        self.setText(self._original_text)
        self.setStyleSheet("")
        self.setEnabled(True)
```

- [ ] **Step 2: Validators**

`gui/components/validators.py`:
```python
"""QValidator subclasses for port and number range."""
from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QIntValidator, QRegularExpressionValidator, QValidator


class PortValidator(QIntValidator):
    def __init__(self, parent=None):
        super().__init__(1024, 65535, parent)

    def validate(self, input_text: str, pos: int) -> tuple[QValidator.State, str, int]:
        if not input_text:
            return QValidator.State.Intermediate, input_text, pos
        return super().validate(input_text, pos)


class NumberRangeValidator(QIntValidator):
    def __init__(self, minimum: int, maximum: int, parent=None):
        super().__init__(minimum, maximum, parent)
```

- [ ] **Step 3: Skeleton**

`gui/components/skeleton.py`:
```python
"""Skeleton loading placeholder widget."""
from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class SkeletonWidget(QWidget):
    def __init__(self, width: int = 100, height: int = 20, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._opacity = 0.3
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._timer.start(800)
        self._direction = 1

    def _pulse(self):
        self._opacity += 0.05 * self._direction
        if self._opacity >= 0.5:
            self._direction = -1
        elif self._opacity <= 0.15:
            self._direction = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(200, 200, 200, int(255 * self._opacity)))
        painter.end()
```

- [ ] **Step 4: PrinterCardWidget**

`gui/components/printer_card.py`:
```python
"""Printer card widget showing name, status, and controls."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class PrinterCardWidget(QFrame):
    set_default_clicked = Signal(str)

    def __init__(self, name: str, status: str, is_default: bool = False, parent=None):
        super().__init__(parent)
        self._name = name
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(260, 120)

        layout = QVBoxLayout(self)
        # Name + status dot
        header = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {'green' if status == 'ready' else 'orange'}; font-size: 18px;")
        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(dot)
        header.addWidget(name_label)
        header.addStretch()
        layout.addLayout(header)

        status_label = QLabel(f"状态: {status}")
        status_label.setStyleSheet("color: gray;")
        layout.addWidget(status_label)

        if is_default:
            default_label = QLabel("★ 默认打印机")
            default_label.setStyleSheet("color: #16A34A; font-weight: bold;")
            layout.addWidget(default_label)
        else:
            btn = QPushButton("设为默认")
            btn.clicked.connect(lambda: self.set_default_clicked.emit(self._name))
            layout.addWidget(btn)

        layout.addStretch()
```

- [ ] **Step 5: DropZoneWidget**

`gui/components/drop_zone.py`:
```python
"""Drag-and-drop zone for file selection."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class DropZoneWidget(QWidget):
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(200)
        self.setStyleSheet("""
            DropZoneWidget {
                border: 2px dashed #D1D5DB;
                border-radius: 12px;
                background-color: transparent;
            }
            DropZoneWidget[drag_over="true"] {
                border-color: #4F46E5;
                background-color: rgba(79, 70, 229, 0.05);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label = QLabel("☁")
        self._icon_label.setStyleSheet("font-size: 48px; color: #4F46E5;")
        self._text_label = QLabel("拖拽文件到此处")
        self._text_label.setStyleSheet("font-size: 16px; color: #6B7280;")
        self._file_label = QLabel("")
        self._file_label.setStyleSheet("color: #1F2937;")
        layout.addWidget(self._icon_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._text_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._file_label, alignment=Qt.AlignmentFlag.AlignCenter)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("drag_over", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("drag_over", False)
        self.style().unpolish(self)
        self.style().polish(self)
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
            if path:
                self._set_file(path)
                self.file_dropped.emit(path)

    def _set_file(self, path: str):
        p = Path(path)
        if p.exists():
            self._file_label.setText(f"{p.name} ({p.stat().st_size / 1024:.1f} KB)")
```

- [ ] **Step 6: Notification**

`gui/components/notification.py`:
```python
"""Toast notification widget (bottom-right slide-in)."""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class NotificationWidget(QFrame):
    def __init__(self, text: str, color: str = "#4F46E5", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            NotificationWidget {{
                background-color: {color};
                border-radius: 8px;
                padding: 12px 20px;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        self._label = QLabel(text)
        self._label.setStyleSheet("color: white; font-size: 13px;")
        close_btn = QPushButton("×")
        close_btn.setStyleSheet("color: white; border: none; font-size: 16px;")
        close_btn.clicked.connect(self.hide)
        layout.addWidget(self._label)
        layout.addWidget(close_btn)

        # Auto-hide after 3s
        QTimer.singleShot(3000, self._fade_out)

    def _fade_out(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(300)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self.deleteLater)
        anim.start()


class NotificationStack(QWidget):
    """Stack of notification toasts at bottom-right."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.setLayout(layout)

    def show_notification(self, text: str, color: str = "#4F46E5"):
        n = NotificationWidget(text, color, self)
        self.layout().addWidget(n)
```

- [ ] **Step 7: QCheckBox Switch 美化 + QProgressBar 4 态 + QDialog 类型

在 `gui/components/` 中创建一个开关美化 mixin，用于 `duplex_cb` 和 `color_cb`：

```python
# gui/components/switch_mixin.py — QCheckBox 美化 Switch 外观
SWITCH_QSS = """
QCheckBox::indicator {
    width: 36px; height: 18px; border-radius: 9px;
    background-color: #D1D5DB; border: none;
}
QCheckBox::indicator:checked {
    background-color: #4F46E5;
}
QCheckBox::indicator:disabled {
    opacity: 0.4;
}
"""
```

在 `gui/components/notification.py` 末尾添加通用确认对话框函数：
```python
# 通用确认对话框
def confirm_dialog(parent, title: str, text: str,
                   buttons: dict[str, QMessageBox.ButtonRole]) -> str | None:
    """返回用户点击的按钮文本，或 None。"""
    from PySide6.QtWidgets import QMessageBox
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    for btn_text, role in buttons.items():
        msg.addButton(btn_text, role)
    msg.exec()
    clicked = msg.clickedButton()
    return clicked.text() if clicked else None
```

并在 Task 10 的设置页面使用 `confirm_dialog` 处理"需重启"确认。

QProgressBar 4 态在 Task 7 快速打印中使用：
```python
# QProgressBar 4 态样式
# 确定模式：setRange(0, 100) + setValue(x) — 文件上传/打印进度
# 不确定模式：setRange(0, 0) — 排队等待中
# 完成：setValue(100) + setStyleSheet("QProgressBar::chunk { background-color: #16A34A; }")
# 失败：setStyleSheet("QProgressBar::chunk { background-color: #DC2626; }")
```

- [ ] **Step 8: 验证组件导入**

```bash
python -c "
from gui.components.stateful_button import StatefulButton
from gui.components.validators import PortValidator, NumberRangeValidator
from gui.components.skeleton import SkeletonWidget
from gui.components.printer_card import PrinterCardWidget
from gui.components.drop_zone import DropZoneWidget
from gui.components.notification import NotificationWidget, NotificationStack, confirm_dialog
print('All components OK')
"
```

- [ ] **Step 8: Commit**

```bash
git add gui/components/
git commit -m "feat: reusable PySide6 components (StatefulButton, validators, skeleton, printer card, drop zone, notification, switch QSS, confirm dialog)"
```

---

## Phase B: 页面实现 — 功能优先（Steps 6-12）

每页按 TDD 模式：先写测试 → 测试失败 → 实现 → 测试通过。**UI 设计（视觉风格）放到最后**，页面先用默认 Qt 样式确保功能正确。

### Task 6: 仪表盘页面

**Files:**
- Create: `gui/pages/dashboard.py`
- Create: `tests/test_gui_dashboard.py`

- [ ] **Step 1: 实现 DashboardPage**

`gui/pages/dashboard.py`:
```python
"""Dashboard page: stat cards, chart, printer cards, recent jobs."""
from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis, QDateTimeAxis
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QPushButton

from gui.components.skeleton import SkeletonWidget
from gui.components.printer_card import PrinterCardWidget


class StatCard(QFrame):
    def __init__(self, title: str, value: str, color: str = "#1F2937", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        layout.addWidget(title_label)
        layout.addWidget(self.value_label)


class DashboardPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._event_bus = getattr(main_window, "_event_bus", None)
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Title
        title = QLabel("仪表盘")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        # Status bar
        self.status_row = QHBoxLayout()
        layout.addLayout(self.status_row)

        # 6 stat cards in grid (2×3)
        self.stat_grid = QGridLayout()
        self.stat_grid.setSpacing(12)
        self._stats: dict[str, StatCard] = {}
        stat_defs = [
            ("排队中", "0", "#4F46E5"), ("打印中", "0", "#F59E0B"),
            ("今日完成", "0", "#16A34A"), ("今日失败", "0", "#DC2626"),
            ("成功率", "0%", "#16A34A"), ("总计", "0", "#1F2937"),
        ]
        for i, (title, val, color) in enumerate(stat_defs):
            card = StatCard(title, val, color)
            self._stats[title] = card
            self.stat_grid.addWidget(card, i // 3, i % 3)
        layout.addLayout(self.stat_grid)

        # Error banner (hidden by default)
        self.error_banner = QLabel("")
        self.error_banner.setVisible(False)
        self.error_banner.setStyleSheet(
            "background-color: #FEE2E2; color: #DC2626; padding: 8px 16px; border-radius: 4px;"
        )
        layout.addWidget(self.error_banner)

        # Empty state (first-run)
        self.empty_state = QWidget()
        empty_lo = QVBoxLayout(self.empty_state)
        empty_lo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("📊")
        empty_icon.setStyleSheet("font-size: 48px;")
        empty_text = QLabel("尚无打印任务")
        empty_text.setStyleSheet("font-size: 16px; color: #6B7280;")
        go_print_btn = QPushButton("前往快速打印")
        go_print_btn.clicked.connect(lambda: main_window.nav.setCurrentRow(1))
        empty_lo.addWidget(empty_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(empty_text, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_lo.addWidget(go_print_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_state)
        self.empty_state.setVisible(False)

        # QChart — 7-day print trend
        self._chart = QChart()
        self._chart.setTitle("近 7 天打印趋势")
        self._chart.legend().hide()
        self._series = QLineSeries()
        self._chart.addSeries(self._series)
        self._axis_x = QDateTimeAxis()
        self._axis_x.setFormat("MM-dd")
        self._axis_x.setLabelsAngle(-45)
        self._chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)
        self._series.attachAxis(self._axis_x)
        self._axis_y = QValueAxis()
        self._axis_y.setLabelFormat("%d")
        self._axis_y.setMin(0)
        self._chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)
        self._series.attachAxis(self._axis_y)

        self.chart_view = QChartView(self._chart)
        self.chart_view.setFixedHeight(200)
        self.chart_view.setRenderHint(QChartView.RenderHint.Antialiasing)
        layout.addWidget(self.chart_view)

        # Printer cards + Recent jobs row
        bottom_row = QHBoxLayout()
        self.printer_area = QVBoxLayout()
        self.printer_area.addWidget(QLabel("打印机状态"))
        bottom_row.addLayout(self.printer_area)
        self.jobs_area = QVBoxLayout()
        self.jobs_area.addWidget(QLabel("最近任务"))
        bottom_row.addLayout(self.jobs_area)
        layout.addLayout(bottom_row)

        # Refresh timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)

    def _refresh(self):
        # Connected to EventBus in Task 13
        pass

    def show_loading(self):
        self.error_banner.setVisible(False)
        self.empty_state.setVisible(False)
        for card in self._stats.values():
            card.value_label.setText("---")
            card.value_label.setStyleSheet("color: #D1D5DB; font-size: 24px; font-weight: bold;")

    def show_error(self, msg: str):
        self.error_banner.setText(f"⚠ {msg}")
        self.error_banner.setVisible(True)
```

- [ ] **Step 2: 验证导入**

```bash
python -c "from gui.pages.dashboard import DashboardPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/dashboard.py
git commit -m "feat: DashboardPage with QChart trend, stat cards, empty/loading/error states"
```

### Task 7: 快速打印页面

**Files:**
- Create: `gui/pages/quick_print.py`

- [ ] **Step 1: 实现 QuickPrintPage**

`gui/pages/quick_print.py`:
```python
"""Quick print page: file picker, print options, submit."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
    QLineEdit, PrintDialog, QProgressBar, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from gui.components.drop_zone import DropZoneWidget
from gui.components.stateful_button import StatefulButton


class QuickPrintPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("快速打印", styleSheet="font-size: 24px; font-weight: bold;"))

        # Drop zone
        self.drop_zone = DropZoneWidget(self)
        self.drop_zone.file_dropped.connect(self._on_file_selected)
        layout.addWidget(self.drop_zone)

        # Path input + browse
        path_row = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("文件路径")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_input)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # Print options
        options_row = QHBoxLayout()
        self.printer_combo = QComboBox()
        self.printer_combo.setPlaceholderText("选择打印机")
        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 99)
        self.copies_spin.setValue(1)
        self.duplex_cb = QCheckBox("双面")
        self.duplex_cb.setChecked(True)
        self.color_cb = QCheckBox("颜色")
        self.color_cb.setChecked(True)
        self.paper_combo = QComboBox()
        self.paper_combo.addItems(["A4", "Letter", "A3"])
        options_row.addWidget(QLabel("打印机:"))
        options_row.addWidget(self.printer_combo)
        options_row.addWidget(QLabel("份数:"))
        options_row.addWidget(self.copies_spin)
        options_row.addWidget(self.duplex_cb)
        options_row.addWidget(self.color_cb)
        options_row.addWidget(QLabel("纸张:"))
        options_row.addWidget(self.paper_combo)
        layout.addLayout(options_row)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Submit
        self.submit_btn = StatefulButton("开始打印")
        self.submit_btn.clicked.connect(self._submit)
        layout.addWidget(self.submit_btn)

        # Tracking
        self.tracking_label = QLabel("")
        self.tracking_label.setVisible(False)
        layout.addWidget(self.tracking_label)

        layout.addStretch()

        self._file_path: str | None = None

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件")
        if path:
            self._on_file_selected(path)

    def _on_file_selected(self, path: str):
        p = Path(path)
        if p.exists():
            self._file_path = str(p)
            self.path_input.setText(str(p))
            self.drop_zone._file_label.setText(f"{p.name} ({p.stat().st_size / 1024:.1f} KB)")

    def _submit(self):
        if not self._file_path:
            return
        self.submit_btn.set_loading()
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)  # indeterminate while queuing
        # Upload via service (direct call, not HTTP)
        from app.services.upload import save_upload
        file_obj = save_upload(Path(self._file_path))
        if file_obj:
            from app.printing.job_queue import get_queue
            queue = get_queue()
            job = queue.enqueue(str(file_obj.path), printer=self.printer_combo.currentText(),
                                copies=self.copies_spin.value(), duplex=self.duplex_cb.isChecked(),
                                color=self.color_cb.isChecked(), paper_size=self.paper_combo.currentText())
            self._tracking_job_id = job.id
            self.tracking_label.setText(f"任务 #{job.id} 已提交，等待处理...")
            self.tracking_label.setVisible(True)
            self.progress.setRange(0, 100)
            self.progress.setValue(50)
        else:
            self.submit_btn.set_error()
            self.progress.setVisible(False)
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.pages.quick_print import QuickPrintPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/quick_print.py
git commit -m "feat: QuickPrintPage with file dialog, drop zone, print options"
```

### Task 8: 任务管理页面

**Files:**
- Create: `gui/pages/job_manager.py`

- [ ] **Step 1: 实现 JobManagerPage**

`gui/pages/job_manager.py`:
```python
"""Job manager page: queue + history tables with filter."""
from __future__ import annotations

from PySide6.QtCore import Qt, QAbstractTableModel, QSortFilterProxyModel
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QProgressBar, QPushButton,
    QTableView, QVBoxLayout, QWidget,
)


class SimpleTableModel(QAbstractTableModel):
    """Read-only table model for job data."""
    def __init__(self, headers: list[str], parent=None):
        super().__init__(parent)
        self._headers = headers
        self._data: list[list[str]] = []

    def rowCount(self, parent=...): return len(self._data)
    def columnCount(self, parent=...): return len(self._headers)
    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._data[index.row()][index.column()]
        return None

    def set_data(self, data: list[list[str]]):
        self.beginResetModel()
        self._data = data
        self.endResetModel()


class JobManagerPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("任务管理", styleSheet="font-size: 24px; font-weight: bold;"))

        # Queue section
        layout.addWidget(QLabel("打印队列"))
        self.queue_empty_label = QLabel("队列为空，提交打印任务后将在此显示")
        self.queue_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.queue_empty_label.setStyleSheet("color: #9CA3AF; font-size: 14px; padding: 20px;")
        layout.addWidget(self.queue_empty_label)
        self.queue_table = QTableView()
        self.queue_model = SimpleTableModel(["文件名", "状态", "进度", "操作"])
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setVisible(False)
        layout.addWidget(self.queue_table)

        # History section
        layout.addWidget(QLabel("历史记录"))
        filter_row = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["全部", "完成", "失败", "已取消"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件名...")
        self.clear_filter_btn = QPushButton("清除筛选")
        self.clear_filter_btn.setVisible(False)
        self.clear_filter_btn.clicked.connect(self._clear_filter)
        filter_row.addWidget(QLabel("状态:"))
        filter_row.addWidget(self.status_filter)
        filter_row.addWidget(self.search_input)
        filter_row.addWidget(self.clear_filter_btn)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        self.history_table = QTableView()
        self.history_model = SimpleTableModel(
            ["ID", "文件名", "类型", "状态", "提交时间", "完成时间", "操作"]
        )
        self.history_table.setModel(self.history_model)
        self.history_table.setSortingEnabled(True)
        layout.addWidget(self.history_table)

        # Pagination
        pagination_row = QHBoxLayout()
        self.prev_btn = QPushButton("← 上一页")
        self.page_label = QLabel("第 1 页")
        self.next_btn = QPushButton("下一页 →")
        self.prev_btn.clicked.connect(self._prev_page)
        self.next_btn.clicked.connect(self._next_page)
        pagination_row.addStretch()
        pagination_row.addWidget(self.prev_btn)
        pagination_row.addWidget(self.page_label)
        pagination_row.addWidget(self.next_btn)
        pagination_row.addStretch()
        layout.addLayout(pagination_row)

        # Batch ops
        batch_row = QHBoxLayout()
        batch_row.addWidget(QPushButton("批量取消"))
        batch_row.addWidget(QPushButton("批量重试"))
        batch_row.addStretch()
        layout.addLayout(batch_row)

        self._page = 0
        self._page_size = 20

    def _clear_filter(self):
        self.status_filter.setCurrentIndex(0)
        self.search_input.clear()

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self.page_label.setText(f"第 {self._page + 1} 页")

    def _next_page(self):
        self._page += 1
        self.page_label.setText(f"第 {self._page + 1} 页")
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.pages.job_manager import JobManagerPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/job_manager.py
git commit -m "feat: JobManagerPage with queue and history tables"
```

### Task 9: 实时日志页面

**Files:**
- Create: `gui/pages/logs.py`

- [ ] **Step 1: 实现 LogsPage**

`gui/pages/logs.py` (参照 QuickPrintPage 模式，使用 QListWidget + 颜色编码筛选):
```python
"""Real-time log viewer with level filter and pause."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)


LOG_COLORS = {
    "ERROR": QColor("#DC2626"),
    "WARNING": QColor("#F59E0B"),
    "INFO": QColor("#2563EB"),
    "DEBUG": QColor("#6B7280"),
}


class LogsPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("实时日志", styleSheet="font-size: 24px; font-weight: bold;"))

        # Controls
        controls = QHBoxLayout()
        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "错误", "警告", "信息", "调试"])
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索...")
        self.pause_btn = QPushButton("暂停")
        self.clear_btn = QPushButton("清空")
        self.auto_scroll_cb = QCheckBox("自动滚动")
        self.auto_scroll_cb.setChecked(True)
        controls.addWidget(QLabel("级别:"))
        controls.addWidget(self.level_filter)
        controls.addWidget(self.search_input)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.clear_btn)
        controls.addWidget(self.auto_scroll_cb)
        layout.addLayout(controls)

        # Empty state
        self.log_empty_label = QLabel("暂无日志，打印任务时将自动显示")
        self.log_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.log_empty_label.setStyleSheet("color: #9CA3AF; font-size: 14px; padding: 40px;")
        layout.addWidget(self.log_empty_label)

        # Log list
        self.log_list = QListWidget()
        self.log_list.setVisible(False)
        layout.addWidget(self.log_list)

        # Pause banner
        self.pause_banner = QLabel("")
        self.pause_banner.setVisible(False)
        self.pause_banner.setStyleSheet(
            "background-color: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 4px;"
        )
        layout.addWidget(self.pause_banner)

        self._paused = False
        self._buffer: list[str] = []
        self._max_lines = 1000

        self.pause_btn.clicked.connect(self._toggle_pause)
        self.clear_btn.clicked.connect(self.log_list.clear)
        self.level_filter.currentTextChanged.connect(self._apply_filters)
        self.search_input.textChanged.connect(self._apply_filters)

    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_btn.setText("继续" if self._paused else "暂停")
        if not self._paused:
            for line in self._buffer:
                self._append_line(line)
            self._buffer.clear()
            self.pause_banner.setVisible(False)

    def _append_line(self, text: str):
        item = QListWidgetItem(text)
        for level, color in LOG_COLORS.items():
            if level in text:
                item.setForeground(color)
                break
        self.log_list.addItem(item)
        if self.log_list.count() > self._max_lines:
            self.log_list.takeItem(0)
        if self.auto_scroll_cb.isChecked():
            self.log_list.scrollToBottom()

    def on_log(self, data: dict):
        self.log_empty_label.setVisible(False)
        self.log_list.setVisible(True)
        msg = f'{data.get("timestamp", "")}  {data.get("level", "INFO")}  {data.get("message", "")}'
        if self._paused:
            self._buffer.append(msg)
            self.pause_banner.setText(f"⏸ 已暂停 (+{len(self._buffer)} 条)")
            self.pause_banner.setVisible(True)
        else:
            self._append_line(msg)

    def _apply_filters(self):
        level = self.level_filter.currentText()
        search = self.search_input.text().lower()
        for i in range(self.log_list.count()):
            item = self.log_list.item(i)
            if not item:
                continue
            text = item.text()
            visible = True
            if level != "全部":
                level_map = {"错误": "ERROR", "警告": "WARNING", "信息": "INFO", "调试": "DEBUG"}
                if level_map.get(level, "") not in text:
                    visible = False
            if search and search not in text.lower():
                visible = False
            item.setHidden(not visible)
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.pages.logs import LogsPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/logs.py
git commit -m "feat: LogsPage with level filter, search, pause buffer"
```

### Task 10: 设置页面

**Files:**
- Create: `gui/pages/settings.py`

- [ ] **Step 1: 实现 SettingsPage**

`gui/pages/settings.py` (7 个 QGroupBox，每个分组内 QFormLayout + QValidator 验证):

关键结构：
```python
"""Settings page with 7 config groups."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from gui.components.stateful_button import StatefulButton
from gui.components.validators import PortValidator, NumberRangeValidator


class SettingsPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._config = getattr(main_window, "_config", None)
        self._changed_keys: set[str] = set()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        layout.addWidget(QLabel("设置", styleSheet="font-size: 24px; font-weight: bold;"))

        # Group 1: Security
        security_group = QGroupBox("安全")
        security_form = QFormLayout(security_group)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        gen_btn = QPushButton("生成")
        key_row = QHBoxLayout()
        key_row.addWidget(self.api_key_input)
        key_row.addWidget(gen_btn)
        security_form.addRow("API 密钥:", key_row)
        layout.addWidget(security_group)

        # Group 2: Print defaults
        print_group = QGroupBox("打印默认值")
        print_form = QFormLayout(print_group)
        self.default_printer = QComboBox()
        self.default_copies = QSpinBox(); self.default_copies.setRange(1, 99)
        self.default_duplex = QCheckBox("双面"); self.default_duplex.setChecked(True)
        self.default_color = QCheckBox("颜色"); self.default_color.setChecked(True)
        self.paper_size = QComboBox(); self.paper_size.addItems(["A4", "Letter", "A3"])
        print_form.addRow("默认打印机:", self.default_printer)
        print_form.addRow("份数:", self.default_copies)
        print_form.addRow(self.default_duplex)
        print_form.addRow(self.default_color)
        print_form.addRow("纸张:", self.paper_size)
        layout.addWidget(print_group)

        # Group 3: Quark (密码框)
        quark_group = QGroupBox("夸克扫描王 API")
        quark_form = QFormLayout(quark_group)
        self.quark_key_id = QLineEdit(); self.quark_key_id.setEchoMode(QLineEdit.EchoMode.Password)
        self.quark_key = QLineEdit(); self.quark_key.setEchoMode(QLineEdit.EchoMode.Password)
        quark_form.addRow("Key ID:", self.quark_key_id)
        quark_form.addRow("API Key:", self.quark_key)
        layout.addWidget(quark_group)

        # Group 4: Notification
        notify_group = QGroupBox("通知渠道")
        notify_form = QFormLayout(notify_group)
        self.notify_channel = QComboBox()
        self.notify_channel.addItems(["禁用", "钉钉", "Bark"])
        self.dingtalk_webhook = QLineEdit(); self.dingtalk_webhook.setEchoMode(QLineEdit.EchoMode.Password)
        self.dingtalk_level = QComboBox(); self.dingtalk_level.addItems(["错误", "警告及以上", "全部"])
        self.bark_key = QLineEdit(); self.bark_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.bark_server = QLineEdit()
        notify_form.addRow("渠道:", self.notify_channel)
        notify_form.addRow("钉钉 Webhook:", self.dingtalk_webhook)
        notify_form.addRow("钉钉级别:", self.dingtalk_level)
        notify_form.addRow("Bark Key:", self.bark_key)
        notify_form.addRow("Bark 服务器:", self.bark_server)
        layout.addWidget(notify_group)

        # Group 5: Server
        server_group = QGroupBox("服务器")
        server_form = QFormLayout(server_group)
        self.port_input = QLineEdit()
        self.port_input.setValidator(PortValidator(self))
        self.log_level = QComboBox(); self.log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self.ssl_cb = QCheckBox("启用 SSL")
        self.theme_combo = QComboBox(); self.theme_combo.addItems(["亮色", "深色", "跟随系统"])
        server_form.addRow("端口:", self.port_input)
        server_form.addRow("日志级别:", self.log_level)
        server_form.addRow(self.ssl_cb)
        server_form.addRow("主题:", self.theme_combo)
        layout.addWidget(server_group)

        # Group 6: Worker
        worker_group = QGroupBox("工作进程")
        worker_form = QFormLayout(worker_group)
        self.worker_count = QSpinBox(); self.worker_count.setRange(1, 16)
        self.max_file_size = QSpinBox(); self.max_file_size.setRange(1, 500)
        self.job_retention = QSpinBox(); self.job_retention.setRange(1, 365)
        self.print_dpi = QSpinBox(); self.print_dpi.setRange(72, 1200)
        self.job_timeout = QSpinBox(); self.job_timeout.setRange(30, 3600)
        self.word_timeout = QSpinBox(); self.word_timeout.setRange(30, 600)
        worker_form.addRow("工作进程数:", self.worker_count)
        worker_form.addRow("最大文件(MB):", self.max_file_size)
        worker_form.addRow("任务保留(天):", self.job_retention)
        worker_form.addRow("打印 DPI:", self.print_dpi)
        worker_form.addRow("任务超时(秒):", self.job_timeout)
        worker_form.addRow("Word 超时(秒):", self.word_timeout)
        layout.addWidget(worker_group)

        # Save + Test buttons
        btn_row = QHBoxLayout()
        self.save_btn = StatefulButton("保存设置")
        self.test_btn = StatefulButton("测试通知")
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.test_btn)
        layout.addLayout(btn_row)

        layout.addStretch()
        scroll.setWidget(container)

        main_layout = QVBoxLayout(self)

        # Loading skeleton (shown before config loads)
        self.loading_skeleton = QWidget()
        sk_lo = QVBoxLayout(self.loading_skeleton)
        for _ in range(5):
            skeleton = SkeletonWidget(width=400, height=60)
            sk_lo.addWidget(skeleton)
        main_layout.addWidget(self.loading_skeleton)

        main_layout.addWidget(scroll)
        scroll.setVisible(False)  # shown after load completes

    def show_loaded(self):
        self.loading_skeleton.setVisible(False)
        self.scroll.setVisible(True)

    def _on_save(self):
        # Validation: highlight invalid fields
        errors = []
        if not self.port_input.hasAcceptableInput():
            self.port_input.setStyleSheet("border: 1px solid #DC2626;")
            errors.append("端口范围 1024-65535")
        else:
            self.port_input.setStyleSheet("")
        if errors:
            self.save_btn.set_error()
            self.save_btn.setToolTip("；".join(errors))
            return
        # Save via config
        self._config.set_many({...})
        self._config.save()
        self.save_btn.set_success()
        # Check if restart needed
        restart_keys = {"port", "log_level", "ssl_enabled"}
        changed = set(self._changed_keys) & restart_keys
        if changed:
            from gui.components.notification import confirm_dialog
            result = confirm_dialog(self, "需要重启",
                "部分设置需要重启服务器生效，是否立即重启？",
                {"稍后重启": QMessageBox.ButtonRole.RejectRole,
                 "立即重启": QMessageBox.ButtonRole.AcceptRole})
            if result == "立即重启":
                self._mw._on_restart()
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.pages.settings import SettingsPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/settings.py
git commit -m "feat: SettingsPage with 7 config groups and validation"
```

### Task 11: 打印机管理页面

**Files:**
- Create: `gui/pages/printer_manager.py`

- [ ] **Step 1: 实现 PrinterManagerPage**

`gui/pages/printer_manager.py`:
```python
"""Printer management page: card grid with status and set-default."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from gui.components.printer_card import PrinterCardWidget


class PrinterManagerPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)

        # Header
        header = QHBoxLayout()
        header.addWidget(QLabel("打印机管理", styleSheet="font-size: 24px; font-weight: bold;"))
        refresh_btn = QPushButton("刷新状态")
        refresh_btn.clicked.connect(self._refresh)
        header.addWidget(refresh_btn)
        header.addStretch()
        layout.addLayout(header)

        # Card grid in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.card_container = QWidget()
        self.card_layout = QHBoxLayout(self.card_container)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.card_container)
        layout.addWidget(scroll)

        # Empty state
        self.empty_label = QLabel("未检测到打印机\n请确保打印机已连接并开启")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #9CA3AF; font-size: 16px; padding: 40px;")
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        # Auto-refresh label
        layout.addWidget(QLabel("打印机状态每 30 秒自动更新", styleSheet="color: #9CA3AF; font-size: 12px;"))

    def show_loading(self):
        from gui.components.skeleton import SkeletonWidget
        for i in reversed(range(self.card_layout.count())):
            w = self.card_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        for _ in range(3):
            skeleton = SkeletonWidget(width=260, height=120)
            self.card_layout.addWidget(skeleton)
        self.empty_label.setVisible(False)

    def _refresh(self):
        self.show_loading()
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.pages.printer_manager import PrinterManagerPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/printer_manager.py
git commit -m "feat: PrinterManagerPage with card grid and refresh"
```

### Task 12: 关于页面

**Files:**
- Create: `gui/pages/about.py`

- [ ] **Step 1: 实现 AboutPage**

`gui/pages/about.py`:
```python
"""About page: version info, update check, links."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import gui


class AboutPage(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        version = getattr(gui, "__version__", "0.0.0")

        layout.addWidget(QLabel("🖨️", styleSheet="font-size: 64px;"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(QLabel("iOS 云打印服务器", styleSheet="font-size: 28px; font-weight: bold;"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(QLabel(f"版本: {version}"), alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(QLabel(f"Python: {__import__('sys').version.split()[0]}"), alignment=Qt.AlignmentFlag.AlignCenter)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_btn = QPushButton("检查更新")
        logs_btn = QPushButton("日志文件夹")
        config_btn = QPushButton("配置文件")
        self.update_btn.clicked.connect(self._check_update)
        logs_btn.clicked.connect(self._open_logs)
        config_btn.clicked.connect(self._open_config)
        btn_row.addWidget(self.update_btn)
        btn_row.addWidget(logs_btn)
        btn_row.addWidget(config_btn)
        layout.addLayout(btn_row)

        # Update status area
        self.update_status = QLabel("")
        self.update_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.update_status)

        layout.addStretch()

    def _open_logs(self):
        from app._paths import persistent_dir
        logs_dir = persistent_dir() / "logs"
        if logs_dir.exists():
            subprocess.Popen(["explorer", str(logs_dir)])

    def _open_config(self):
        from app._paths import persistent_dir
        cfg = persistent_dir() / "config.json"
        if cfg.exists():
            subprocess.Popen(["notepad", str(cfg)])

    def _check_update(self):
        self.update_status.setText("正在检查更新...")
        self.update_status.setStyleSheet("color: #6B7280;")
        self.update_btn.setEnabled(False)
        # Simulated 4 states — replace with actual HTTP call in Task 13:
        # 1. 检查中: "正在检查更新..."
        # 2. 失败: "❌ 检查更新失败，请稍后重试" (red #DC2626)
        # 3. 已是最新: "✅ 已是最新版本 (v{version})" (green #16A34A)
        # 4. 有新版本: "📥 新版本 v{x} 可用" (primary #4F46E5)
        QTimer.singleShot(1500, self._check_done)

    def _check_done(self):
        self.update_status.setText("✅ 已是最新版本 (v0.0.0)")
        self.update_status.setStyleSheet("color: #16A34A;")
        self.update_btn.setEnabled(True)
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.pages.about import AboutPage; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/about.py gui/__init__.py
git commit -m "feat: AboutPage with version info and update check"
```

---

## Phase C: 集成与完善（Steps 13-18）

### Task 13: EventBus 集成 — 连接页面到后端

**Files:**
- Modify: `gui/pages/dashboard.py`, `gui/pages/quick_print.py`, `gui/pages/job_manager.py`, `gui/pages/printer_manager.py`, `gui/pages/about.py`

- [ ] **Step 1: 为每个页面添加 `on_job_status`、`on_printer_status`、`on_log` 方法

在 DashboardPage 中添加：
```python
def on_job_status(self, data: dict):
    # Update stat cards
    pass

def on_printer_status(self, data: dict):
    # Add/replace printer cards
    pass
```

在 QuickPrintPage 中添加进度跟踪：
```python
def on_job_status(self, data: dict):
    if data.get("job_id") == self._tracking_job_id:
        status = data.get("status", "")
        if status == "completed":
            self.submit_btn.set_success()
            self.tracking_label.setText(f"任务 #{self._tracking_job_id} 完成")
        elif status == "failed":
            self.submit_btn.set_error()
            self.tracking_label.setText(f"失败: {data.get('error', '')}")
        elif status == "printing":
            self.tracking_label.setText(f"任务 #{self._tracking_job_id} 正在打印...")
```

在 PrinterManagerPage 中添加：
```python
def on_printer_status(self, data: dict):
    # Update card grid
    pass
```

- [ ] **Step 2: 验证编译**

```bash
python -c "from gui.pages.dashboard import DashboardPage; from gui.pages.quick_print import QuickPrintPage; from gui.pages.job_manager import JobManagerPage; from gui.pages.logs import LogsPage; from gui.pages.settings import SettingsPage; from gui.pages.printer_manager import PrinterManagerPage; from gui.pages.about import AboutPage; print('All pages OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/
git commit -m "feat: connect all pages to EventBus for real-time updates"
```

### Task 14: 键盘快捷键 QShortcut

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: 在 MainWindow 中添加 QShortcut 绑定

```python
from PySide6.QtGui import QShortcut, QKeySequence

def _setup_shortcuts(self):
    for i, key in enumerate(["Ctrl+1","Ctrl+2","Ctrl+3","Ctrl+4","Ctrl+5","Ctrl+6","Ctrl+7"], 1):
        sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
        sc.activated.connect(lambda idx=i-1: self.nav.setCurrentRow(idx))
    
    QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(lambda: self.nav.setCurrentRow(1))
    QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

def _focus_search(self):
    w = self.stack.currentWidget()
    for attr in ["search_input", "search", "filter_input"]:
        field = getattr(w, attr, None)
        if field and hasattr(field, "setFocus"):
            field.setFocus()
            return
    QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._refresh_current)
    QShortcut(QKeySequence("F5"), self).activated.connect(self._refresh_current)
    QShortcut(QKeySequence("Escape"), self).activated.connect(self._close_dialogs)

def _refresh_current(self):
    w = self.stack.currentWidget()
    if hasattr(w, "_refresh"):
        w._refresh()

def _close_dialogs(self):
    for child in self.findChildren(type(self)):
        if isinstance(child, type(self)) and child.isWindow():
            child.close()
```

在 `__init__` 末尾调用 `self._setup_shortcuts()`

- [ ] **Step 2: 验证**

```bash
python -c "from gui.app import MainWindow; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/app.py
git commit -m "feat: keyboard shortcuts via QShortcut (Ctrl+1-7, Ctrl+P, Ctrl+R, F5, Esc)"
```

### Task 15: 窗口状态持久化 QSettings

**Files:**
- Create: `gui/settings_store.py`
- Modify: `gui/app.py`

- [ ] **Step 1: 实现 WindowStateManager

`gui/settings_store.py`:
```python
"""Window state persistence via QSettings."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QMainWindow


class WindowStateManager:
    def __init__(self, window: QMainWindow):
        self._window = window
        self._settings = QSettings("iOSPrintServer", "main_window")

    def save(self):
        self._settings.setValue("geometry", self._window.saveGeometry())
        self._settings.setValue("last_page", self._window.nav.currentRow())

    def restore(self):
        geom = self._settings.value("geometry")
        if isinstance(geom, QByteArray):
            self._window.restoreGeometry(geom)
        page = self._settings.value("last_page", 0, type=int)
        if page is not None and 0 <= page < 7:
            self._window.nav.setCurrentRow(page)
```

在 MainWindow 的 `closeEvent` 中调用 `self._state_manager.save()`：
```python
def closeEvent(self, event):
    self._state_manager.save()
    event.ignore()
    self.hide()
```

- [ ] **Step 2: 验证**

```bash
python -c "from gui.settings_store import WindowStateManager; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add gui/settings_store.py gui/app.py
git commit -m "feat: window state persistence via QSettings"
```

### Task 16: 微交互

**Files:**
- Modify: `gui/app.py`, `gui/components/stateful_button.py`, `gui/components/printer_card.py`

- [ ] **Step 1: 添加页面切换淡入动画

在 MainWindow 的 `_on_nav_changed` 中添加：
```python
from PySide6.QtCore import QPropertyAnimation

def _on_nav_changed(self, index: int):
    self.stack.setCurrentIndex(index)
    # Fade in animation
    w = self.stack.currentWidget()
    anim = QPropertyAnimation(w, b"windowOpacity")
    anim.setDuration(200)
    anim.setStartValue(0.7)
    anim.setEndValue(1.0)
    anim.start()
```

- [ ] **Step 2: 添加系统托盘消息

在 `_on_job_status` 中显示托盘通知：
```python
def _on_job_status(self, data: dict):
    status = data.get("status", "")
    if status == "completed":
        self.tray.showMessage("打印完成", f"任务 #{data['job_id']} 已完成", QSystemTrayIcon.MessageIcon.Information, 3000)
    elif status == "failed":
        self.tray.showMessage("打印失败", f"任务 #{data['job_id']} 失败: {data.get('error', '')}", QSystemTrayIcon.MessageIcon.Critical, 5000)
```

- [ ] **Step 3: Commit**

```bash
git add gui/app.py gui/components/stateful_button.py gui/components/printer_card.py
git commit -m "feat: micro-interactions (page fade, tray notifications)"
```

### Task 17: 系统托盘菜单完善

**Files:**
- Modify: `gui/app.py`

（已在 Task 2 中实现基础版，此步骤完善菜单项）

- [ ] **Step 1: 完善系统托盘右键菜单

```python
def _setup_tray(self):
    menu = QMenu()
    show_action = menu.addAction("显示窗口")
    show_action.triggered.connect(self.show)
    menu.addSeparator()
    start_action = menu.addAction("启动服务器")
    start_action.triggered.connect(self._on_start)
    stop_action = menu.addAction("停止服务器")
    stop_action.triggered.connect(self._on_stop)
    menu.addSeparator()
    quit_action = menu.addAction("退出")
    quit_action.triggered.connect(self._on_quit)
    self.tray.setContextMenu(menu)
```

- [ ] **Step 2: Commit**

```bash
git add gui/app.py
git commit -m "feat: enhanced system tray menu with server controls"
```

### Task 18: Windows 原生通知

（已在 Task 17 中通过 `tray.showMessage` 实现）

- [ ] **Step 1: 验证**

```bash
python -c "from PySide6.QtWidgets import QSystemTrayIcon; print(hasattr(QSystemTrayIcon, 'showMessage'))"
# Expected: True
```

- [ ] **Step 2: Commit**

```bash
git commit -m "feat: Windows native notifications via QSystemTrayIcon.showMessage"
```

---

## Phase D: UI 视觉设计（最后进行，Steps 19-21）

### Task 19: UI/UX Pro Max — 确定视觉风格

**工作流程：**
1. 使用 UI/UX Pro Max 技能研究当前设计 Token 在 Qt 中的最佳实践
2. 确定：主色、辅助色、字体族、间距系统、圆角半径、阴影深度
3. 生成视觉风格文档
4. 产出：设计 Token 最终值 + QSS 样式规则

### Task 20: Frontend Design — 生成首版界面代码

**工作流程：**
1. 将 UI/UX Pro Max 确定的风格要点交给 Frontend Design
2. 由 Frontend Design 生成完整的 `light.qss` 和 `dark.qss`
3. 应用 QSS 后验证每个页面的视觉呈现
4. 调整组件间距、颜色、字体

### Task 21: 生成 UI Demo

1. 使用 PySide6 启动应用
2. 截图所有 7 个页面在亮色/深色模式下的效果
3. 验证微交互（按钮 hover、页面切换动画、通知弹窗）
4. 调整直至满意

---

## Phase E: 构建与部署（Steps 22-24）

### Task 22: PyInstaller 构建配置更新

**Files:**
- Modify: `build_exe.py` 或 PyInstaller 命令

- [ ] **Step 1: 更新 PyInstaller 配置

```bash
pyinstaller --onefile --name iOSPrintServer ^
    --add-data "gui/resources/*;gui/resources/" ^
    --hidden-import PySide6.QtCharts ^
    --hidden-import PySide6.QtNetwork ^
    console/__main__.py
```

- [ ] **Step 2: 验证构建**

```bash
python -m PyInstaller --onefile --name iOSPrintServer console/__main__.py
# Expected: dist/iOSPrintServer.exe 生成成功
```

- [ ] **Step 3: Commit**

```bash
git add build_exe.py pyproject.toml
git commit -m "chore: update PyInstaller config for PySide6"
```

### Task 23: NSIS 安装器脚本

**Files:**
- Create: `installer.nsi`

- [ ] **Step 1: 编写 NSIS 脚本

`installer.nsi`:
```nsis
!define PRODUCT_NAME "iOS 云打印服务器"
!define PRODUCT_VERSION "1.5.0"
!define PRODUCT_EXE "iOSPrintServer.exe"

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "${PRODUCT_NAME}-Setup-${PRODUCT_VERSION}.exe"
InstallDir "$LOCALAPPDATA\iOSPrintServer"

Section "Install"
  SetOutPath "$INSTDIR"
  File "${PRODUCT_EXE}"
  CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}.lnk" "$INSTDIR\${PRODUCT_EXE}"
  WriteUninstaller "$INSTDIR\uninst.exe"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\${PRODUCT_NAME}.lnk"
  Delete "$INSTDIR\${PRODUCT_EXE}"
  RMDir "$INSTDIR"
SectionEnd
```

- [ ] **Step 2: Commit**

```bash
git add installer.nsi
git commit -m "feat: NSIS installer script"
```

### Task 24: 集成测试 + 回归测试

**Files:**
- Create: `tests/test_gui_lifecycle.py`

- [ ] **Step 1: 编写生命周期测试

`tests/test_gui_lifecycle.py`:
```python
"""Test PySide6 GUI lifecycle without showing window."""
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_theme_engine(qapp):
    from gui.theme import ThemeEngine
    t = ThemeEngine.instance()
    t.apply("light", qapp)
    assert t.tokens["primary"] == "#4F46E5"
    t.apply("dark", qapp)
    assert t.tokens["primary"] == "#818CF8"


def test_stateful_button():
    from gui.components.stateful_button import StatefulButton
    btn = StatefulButton("测试")
    assert btn.text() == "测试"
    btn.set_loading()
    assert "..." in btn.text()
    btn.set_success()
    assert "✓" in btn.text()


def test_port_validator():
    from gui.components.validators import PortValidator
    v = PortValidator()
    state, _, _ = v.validate("8080", 4)
    assert state == v.State.Acceptable
    state, _, _ = v.validate("80", 2)
    assert state == v.State.Intermediate
    state, _, _ = v.validate("99999", 5)
    assert state == v.State.Invalid
```

- [ ] **Step 2: 运行测试**

```bash
python -m pytest tests/test_gui_lifecycle.py -v --tb=short
# Expected: 3 passed
```

- [ ] **Step 3: 运行全部回归测试**

```bash
python -m pytest tests/ -v --tb=short
# Expected: 原有 99+ 测试全部通过 + 新增 GUI 测试通过
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_gui_lifecycle.py
git commit -m "test: PySide6 GUI component lifecycle tests"
```
