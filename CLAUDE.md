# iOS 云打印服务器

Windows 打印服务器，接收 iOS Scriptable 和 Web 请求，通过 pywin32 驱动本地打印机。

## 技术栈

- **FastAPI 0.136+** / Starlette 1.0 / Uvicorn 0.46
- **pydantic 2.x** + **pydantic-settings 2.x** — 配置管理和 API schema
- **pywin32** — Windows COM 组件（Word/Excel/PowerPoint）+ win32print
- **Jinja2** — 管理后台模板（HTMX 驱动）
- **SQLite** (WAL 模式) — 任务持久化
- **loguru** — 日志
- **PySide6 6.8+** — 桌面 GUI 控制台（QMainWindow + QSystemTrayIcon）
- **Scriptable (iOS)** — JavaScript 客户端，WebSocket + HTTP 轮询混合等待

## 项目结构

```
app/
├── __init__.py              # FastAPI 应用工厂
├── bootstrap.py             # 初始化所有服务并组装 app
├── config.py                # 配置管理 (pydantic-settings BaseSettings)
├── auth.py                  # API Key 认证
├── logging.py               # 日志配置
├── schemas.py               # Pydantic 请求/响应模型 — 自动 OpenAPI
├── utils.py                 # 工具函数
├── _paths.py                # 路径管理
├── printing/
│   ├── engine.py            # 打印引擎 — 按文件类型分发到后端
│   ├── job_queue.py         # 任务队列 — 入队/取消/状态/心跳恢复/工作线程
│   ├── repository.py        # SQLite 持久化
│   └── backends.py          # 打印后端 (PDF/Office/Image)
├── routes/
│   ├── api.py               # JSON API 路由
│   ├── admin.py             # 管理后台路由 (HTMX)
│   └── ws.py                # WebSocket /ws/events 端点
├── services/
│   ├── sse_broadcaster.py   # EventBus + SSEBroadcaster 事件系统
│   ├── bark.py              # Bark 推送通知
│   ├── dingtalk.py          # 钉钉机器人通知
│   ├── notifier.py          # 通知抽象 + 错误文案匹配
│   ├── printer_monitor.py   # 打印机状态监听
│   ├── printer_discovery.py # 打印机发现服务
│   ├── log_broadcaster.py   # 日志实时推送
│   ├── heartbeat.py         # 心跳：清理过期任务 / 恢复卡住任务
│   └── upload.py            # 文件上传校验 + 保存 + 入队
└── templates/admin/         # Jinja2 管理后台模板
```

## 架构决策

### 事件系统（EventBus + SSEBroadcaster）

```
EventBus:     on/off/publish      — 服务间本地解耦（JobQueue → Notifier）
SSEBroadcaster: subscribe/unsubscribe/publish  — SSE/WS 远程推送
               同时委托 EventBus 处理本地监听
```

- 服务（JobQueue、WorkerPool、PrinterMonitor）只注入 `EventBus`，只调 `publish()`
- Notifier 回调通过 `SSEBroadcaster.on()` 注册（兼容旧用法）
- `init_app()` 同时注册 `app.state.event_bus` 和 `app.state.sse`

### 配置管理

- `Config(BaseSettings)` 单类，`.env` + `config.json` 双层加载
- 环境变量优先于 JSON 文件（检测方式：创建 `_skip_file=True` 的临时实例对比）
- 运行时修改通过 `config.set()` / `config.set_many()` + `config.save()`

### 打印并发

- `JobQueue` 内联 Worker 线程（替代 `WorkerPool` + `JobWorker` + `JobExecutor` + `RetryHandler`）
- 共享 `ThreadPoolExecutor(max_workers=4)` 实现打印超时隔离，按 1 秒轮询检测取消
- Office COM 组件串行访问（`word_lock` / `excel_lock` / `ppt_lock`）
- 每个 Worker 线程需 `pythoncom.CoInitialize()` / `CoUninitialize()`

### 通知

- `notify_channel`: `disabled` | `dingtalk` | `bark`，通过 `Notifier` 抽象接口解耦
- 事件驱动：Worker → `event_bus.publish('job_status')` → bootstrap 注册的回调 → Notifier
- `test_notification` 端点通过 `BackgroundTasks` 异步发送，不阻塞 HTTP 响应

### Scriptable (iOS) 客户端

- WebSocket 优先等待 + 8s 超时降级为 HTTP 轮询
- 多文件使用 `Promise.allSettled` 并行等待所有任务
- iOS Scriptable 不支持 EventSource（SSE），需要用 WebSocket 替代

### 管理后台

- HTMX 驱动，JSON 端点 + HTML 片段响应
- SSE 实时推送（日志/任务状态/打印机状态）
- 模板引擎 Jinja2，兼容 Flask `url_for` 语法

## 代码规范

- **pydantic v2**: 使用 `model_dump()` / `model_copy()`，非 v1 的 `dict()` / `copy()`
- **PrivateAttr**: pydantic 私有字段用 `PrivateAttr`，自动排除于 `model_dump`
- **无死代码**: 不保留未使用的 import、函数、文件、注释掉的代码
- **无多余注释**: 只写 WHY 不写 WHAT，好命名胜过注释
- **线程安全**: 共享状态用 `threading.Lock`，事件发布用 `EventBus`
- **FastAPI 路由**: JSON 端点标注 `response_model`，自动生成 OpenAPI 文档

## 测试

- `python -m pytest tests/ -v --tb=short`
- 99 个测试覆盖：上传、WorkerPool、SSEBroadcaster、配置、工具函数、JobQueue、Heartbeat

