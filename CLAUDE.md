搜索使用tavily - tavily_search (MCP)
查看技术文档（框架，代码语言，库，组件等）使用context7（MCP）检索API结果
使用Filesystem MCP读取文件。
使用UTF-8编码


# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
# iOS 云打印服务器

Windows 打印服务器，接收 iOS Scriptable 和 Web 请求，通过 pywin32 驱动本地打印机。

## 技术栈

- **FastAPI 0.136+** / Starlette 1.0 / Uvicorn 0.46 — Web 框架 + ASGI 服务器
- **pydantic 2.x** + **pydantic-settings 2.x** — 配置管理和 API schema
- **pywin32** — Windows COM 组件（Word/Excel/PowerPoint）+ win32print
- **PyMuPDF** — PDF 渲染、文本提取、图片转换
- **Pillow 12+** + **pillow-heif** — 图片处理与 HEIC 支持
- **httpx** — 全局 HTTP 客户端（通知推送、更新下载）
- **loguru** — 日志
- **watchfiles** — config.json 热加载
- **PySide6 6.8+** — 桌面 GUI 控制台（QMainWindow + QSystemTrayIcon）
- **SQLite** (WAL 模式) — 任务持久化
- **Scriptable (iOS)** — JavaScript 客户端，WebSocket + HTTP 轮询混合等待

## 项目结构

```
app/
├── __init__.py              # FastAPI 应用工厂 (create_app)
├── bootstrap.py             # 初始化所有服务并组装 app
├── logging.py               # 日志配置 (loguru)
├── resources.py             # 资源目录管理（frozen/dev 双模式）
├── updater.py               # 更新检查器 — GitHub Pages manifest + NSIS 静默安装
├── core/
│   ├── __init__.py
│   ├── _paths.py            # 路径管理 (app_root/config_dir/persistent_dir/log_dir)
│   ├── auth.py              # API Key 认证
│   ├── config.py            # 配置管理 (pydantic-settings BaseSettings)
│   ├── exceptions.py        # 自定义异常 (AuthError/FileTypeError/PrintServerError)
│   ├── schemas.py           # Pydantic 请求/响应模型 — 自动 OpenAPI
│   ├── utils.py             # 工具函数
│   └── version.py           # 版本号读取 (version.txt / git tag / 环境变量)
├── printing/
│   ├── __init__.py
│   ├── engine.py            # 打印引擎 — 按文件类型分发到后端
│   ├── job_queue.py         # 任务队列 — 入队/取消/状态/心跳恢复/工作线程
│   ├── repository.py        # SQLite 持久化
│   ├── image_merger.py      # 多图片合并 PDF
│   ├── enhancer.py          # 图片增强 (Quark API)
│   ├── ipp_client.py        # IPP 协议客户端
│   ├── migrations.py        # 数据库迁移
│   ├── stats.py             # 统计
│   ├── utils.py             # 打印工具函数
│   └── backends/
│       ├── __init__.py
│       ├── base.py          # PrinterBackend 抽象基类 + discover_backends + register
│       ├── image.py         # 图片打印后端
│       ├── office.py        # Office (Word/Excel/PPT) 打印后端
│       ├── pdf.py           # PDF 打印后端
│       ├── pdf_render.py    # PDF 渲染（页码水印等）
│       └── text.py          # 文本打印后端
├── routes/
│   ├── __init__.py
│   ├── api.py               # JSON API 路由 (print/upload/cancel/status/printers)
│   ├── system.py            # 系统路由 (health/version/logs/stats)
│   └── ws.py                # WebSocket /ws/events 端点
└── services/
    ├── __init__.py
    ├── sse_broadcaster.py   # EventBus + SSEBroadcaster 事件系统
    ├── log_broadcaster.py   # 日志实时推送
    ├── heartbeat.py         # 心跳：清理过期任务 / 恢复卡住任务
    ├── printer_monitor.py   # 打印机状态监听 (win32print 轮询)
    ├── upload.py            # 文件上传校验 + 保存 + 入队
    ├── image_processing.py  # 图片增强 (QuarkEnhancer)
    ├── notifier.py          # 通知服务 re-export（向后兼容）
    ├── bark.py              # (旧路径) Bark 推送通知 — 已迁移到 notifications/
    ├── dingtalk.py          # (旧路径) 钉钉机器人通知 — 已迁移到 notifications/
    └── notifications/
        ├── __init__.py      # Notifier 抽象 + HttpNotifier mixin + 错误文案工具
        ├── bark.py          # Bark 推送通知实现
        └── dingtalk.py      # 钉钉机器人通知实现

gui/                         # PySide6 桌面 GUI
├── app.py                   # MainWindow (SidebarWidget + QStackedWidget + 系统托盘)
├── event_bridge.py          # 事件桥接 (GUI ← SSE)
├── http_client.py           # HTTP 客户端封装
├── pipe_client.py           # TCP 客户端 → Go 更新服务
├── settings_store.py        # 设置持久化
├── state.py                 # GUI 状态管理
├── theme.py                 # 主题
├── components/              # 可复用 UI 组件
│   ├── sidebar.py, drop_zone.py, file_item.py, printer_card.py,
│   │   printer_combo.py, print_dialog.py, setup_wizard.py, ...
└── pages/                   # 页面
    ├── dashboard.py, quick_print.py, job_manager.py, logs.py,
    │       │   scan.py, settings.py, about.py, update.py

launcher/                    # 启动入口
├── __init__.py              # 单进程启动 PySide6 GUI + uvicorn
├── __main__.py              # python -m launcher
├── _server.py               # ServerHandle (uvicorn 子线程管理)
└── autostart.py             # 开机自启管理

service/                     # Go 更新服务 (update_service.exe)
├── main.go                  # Windows 服务入口 (golang.org/x/sys/windows/svc)
├── handler.go               # 服务生命周期 (Start/Stop)
├── pipe.go                  # TCP pipe IPC (127.0.0.1:48273)
├── updater.go               # 自动更新：下载/原子替换/回滚
├── checker.go               # GitHub 版本检查
└── go.mod / go.sum

tests/                       # 39 个测试文件
├── conftest.py              # 共享 fixtures (mock_config, sse_broadcaster, app_instance...)
├── test_routes_api.py       # API 路由集成测试
├── test_routes_api_full.py  # API 路由全覆盖测试
├── test_job_queue.py        # 任务队列测试
├── test_sse_broadcaster.py  # SSE 事件系统测试
├── test_config.py           # 配置管理测试
├── test_heartbeat.py        # 心跳测试
├── test_notification_services.py  # 通知服务测试
├── test_backends_*.py       # 各打印后端测试
├── test_print_engine.py     # 打印引擎测试
├── test_e2e_flow.py         # 端到端流测试
├── test_updater.py          # 更新器测试
├── test_gui_lifecycle.py    # GUI 生命周期测试
└── ...

build/                       # 构建输出
├── resources/               # 构建资源文件
├── iOSPrintServer/          # 打包输出目录
└── ...
```

## 架构决策

### 事件系统（EventBus + SSEBroadcaster）

```
EventBus:     on/off/publish      — 服务间本地解耦（JobQueue → Notifier）
SSEBroadcaster: subscribe/unsubscribe/publish  — SSE/WS 远程推送
               同时委托 EventBus 处理本地监听
```

- 服务（JobQueue、PrinterMonitor）只注入 `SSEBroadcaster`，只调 `publish()`
- Notifier 回调通过 `broadcaster.on()` 注册
- `init_app()` 注册 `app.state.sse`

### 配置管理

- `Config(BaseSettings)` 单类，`.env` + `config.json` 双层加载
- 环境变量优先于 JSON 文件（检测方式：创建 `_skip_file=True` 的临时实例对比）
- 运行时修改通过 `config.set()` / `config.set_many()` + `config.save()`
- config.json 变化通过 `watchfiles` 自动重载

### 打印并发

- `JobQueue` 内联 Worker 线程（替代 `WorkerPool` + `JobWorker` + `JobExecutor` + `RetryHandler`）
- 共享 `ThreadPoolExecutor(max_workers=4)` 实现打印超时隔离，按 1 秒轮询检测取消
- Office COM 组件串行访问（`word_lock` / `excel_lock` / `ppt_lock`）
- 每个 Worker 线程需 `pythoncom.CoInitialize()` / `CoUninitialize()`

### 通知

- `notify_channel`: `disabled` | `dingtalk` | `bark`，通过 `Notifier` 抽象接口解耦
- 事件驱动：Worker → `event_bus.publish('job_status')` → bootstrap 注册的回调 → Notifier
- `test_notification` 端点通过 `BackgroundTasks 异步发送
- 通知模块位于 `app/services/notifications/`，`notifier.py` 是向后兼容的 re-export

### Scriptable (iOS) 客户端

- WebSocket 优先等待 + 8s 超时降级为 HTTP 轮询
- 多文件使用 `Promise.allSettled` 并行等待所有任务
- iOS Scriptable 不支持 EventSource（SSE），需要用 WebSocket 替代

### GUI 桌面

- PySide6 QMainWindow + SidebarWidget + QStackedWidget 页面切换
- QSystemTrayIcon 系统托盘，后台运行
- SSE 事件桥接 (`EventBridge`) 连接 GUI 与服务器事件流
- `launcher/` 单进程启动 GUI + uvicorn 子线程

### 更新机制（双栈）

- **Python 端** (`app/updater.py`)：启动时检查 GitHub Pages manifest，下载 NSIS 安装包静默安装
- **Go 服务端** (`service/`)：Windows SYSTEM 服务，TCP IPC 通信，后台检查更新 + 原子替换 + 回滚

### 路径分层

- `app_root()` — exe 所在目录（只读程序文件）
- `config_dir()` — 用户配置（漫游），`%APPDATA%/iOSPrintServer`
- `persistent_dir()` — 可写数据（本机），`%LOCALAPPDATA%/iOSPrintServer`
- `log_dir()` — 日志统一目录，`%PROGRAMDATA%/iOSPrintServer/logs/`

## 代码规范

- **pydantic v2**: 使用 `model_dump()` / `model_copy()`，非 v1 的 `dict()` / `copy()`
- **PrivateAttr**: pydantic 私有字段用 `PrivateAttr`，自动排除于 `model_dump`
- **无死代码**: 不保留未使用的 import、函数、文件、注释掉的代码
- **无多余注释**: 只写 WHY 不写 WHAT，好命名胜过注释
- **线程安全**: 共享状态用 `threading.Lock`，事件发布用 `SSEBroadcaster`
- **FastAPI 路由**: JSON 端点标注 `response_model`，自动生成 OpenAPI 文档

## 测试

- `python -m pytest tests/ -v --tb=short`
- 39 个测试文件，覆盖：上传、JobQueue、SSEBroadcaster、配置、打印后端、通知服务、心跳、更新器、GUI 生命周期


