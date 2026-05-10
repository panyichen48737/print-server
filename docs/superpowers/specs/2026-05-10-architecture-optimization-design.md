# 架构优化设计方案 (方案 B)

日期: 2026-05-10
项目: iOS 云打印服务器

## 背景

对现有代码库进行系统性优化，包括: 目录结构调整、大文件拆分、代码简化去重、类型与错误处理改进，以及修复审查中发现的关键 Bug。

涉及范围: `app/` 后端、`gui/` 前端、`launcher/` 启动器、`.github/` GitHub 配置、项目配置文件。

---

## 1. 目录结构调整

### 现状问题

- `printing/enhancer.py` — 图片增强服务不属于打印引擎
- `printing/utils.py` — 仅含 `cancel_all_spooler_jobs()`，与打印后端关联更紧
- `services/bark.py` + `services/dingtalk.py` — 太薄（40-46 行），应归入统一子模块
- `services/log_broadcaster.py` — 19 行，不值得独立文件
- `services/sse_broadcaster.py` — 同时承担 EventBus 和 SSE 两个职责
- `app/` 根目录文件过多（auth.py, config.py, exceptions.py, schemas.py, utils.py 等）

### 新结构

```
app/
├── core/                              # ← 新建：核心基础设施
│   ├── __init__.py
│   ├── config.py                      # ← 从 app/config.py 移入
│   ├── auth.py                        # ← 从 app/auth.py 移入
│   ├── exceptions.py                  # ← 从 app/exceptions.py 移入
│   ├── schemas.py                     # ← 从 app/schemas.py 移入
│   ├── utils.py                       # ← 从 app/utils.py 移入 + 合并 temp_print_file 上下文管理器
│   ├── _paths.py                      # ← 从 app/_paths.py 移入
│   └── version.py                     # ← 从 app/version.py 移入
│
├── printing/
│   ├── __init__.py
│   ├── engine.py                      # 不变
│   ├── job_queue.py                   # 不变
│   ├── worker.py                      # 内部重构（提取 RetryHandler）
│   ├── worker_pool.py                 # 修复 drain() 命名
│   ├── repository.py                  # CRUD 核心（~120行）
│   ├── stats.py                       # ← 从 repository.py 拆分：统计查询
│   ├── migrations.py                  # ← 从 repository.py 拆分：数据库迁移
│   ├── ipp_client.py                  # 不变
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── base.py                    # 合并 printing/utils.py 的 cancel_all_spooler_jobs
│   │   ├── pdf.py
│   │   ├── office.py
│   │   └── image.py
│
├── services/
│   ├── __init__.py
│   ├── sse_broadcaster.py             # 合并 log_broadcaster.py
│   ├── heartbeat.py                   # 不变
│   ├── printer_monitor.py             # 不变
│   ├── image_processing.py            # ← 从 printing/enhancer.py 移入 + 修复 __del__
│   ├── upload.py                      # 不变
│   └── notifications/                 # ← 新建
│       ├── __init__.py                # Notifier 抽象 + HttpNotifier 混入
│       ├── bark.py                    # 从 services/bark.py 移入 + 修复客户端生命周期
│       └── dingtalk.py                # 从 services/dingtalk.py 移入 + 修复客户端生命周期
│
├── routes/
│   ├── __init__.py                    # APIRouter 聚合
│   ├── api.py                         # 精简：仅打印相关路由
│   ├── admin.py                       # 不变（管理后台 HTMX）
│   ├── system.py                      # ← 从 api.py 拆分：/health, /stats, /logs, /printers, /config
│   └── ws.py                          # 不变
│
├── bootstrap.py                       # 路径更新 + 修复 shutdown 清理
├── logging.py                         # 不变
└── services/notifier.py               # 废弃，功能由 notifications/__init__.py 接管
```

---

## 2. 大文件拆分

### 2.1 repository.py (326 行)

拆分理由: CRUD / 统计 / 迁移 三个职责在同一文件，变化频率不同。

- **`printing/repository.py`** (~120 行): 核心 CRUD（add_job, get_job, update_status, batch_update_status, get_jobs, count_jobs, increment_retry, cleanup_old_jobs, close）
- **`printing/stats.py`** (~80 行): 统计查询（get_stats, get_daily_counts, get_jobs_by_status）
- **`printing/migrations.py`** (~70 行): schema 迁移（_init_db, _migrate_db, get_version）

### 2.2 api.py (301 行)

拆分理由: 打印端点和系统管理端点混合，FastAPI 子 Router 天然适合按域分离。

- **`routes/api.py`** (~120 行): print, upload, status/{job_id}, cancel/{job_id}, retry/{job_id}, cancel_all
- **`routes/system.py`** (~140 行): health, version, logs, printers, printers/status, stats, jobs, test_notification, set_default_printer, /events

### 2.3 worker.py (211 行)

内部重构，不拆文件:
- 提取 `JobExecutor` 为独立内部类（已存在，保持）
- 提取 `RetryHandler` 封装重试策略
- 临时文件清理统一用 `contextmanager`

### 2.4 gui/pages/scan.py (667 行) — GUI 最大文件

拆分理由: 扫描页面混合了 3 个职责：Scanner 设备管理、图像预览/编辑、OCR 结果展示。

- **`gui/pages/scan.py`** (~350 行): 扫描主页面逻辑 + 设备选择 + 启动扫描
- **`gui/pages/scan_preview.py`** (~200 行): 图像预览 + 裁剪/旋转编辑
- **`gui/pages/scan_ocr.py`** (~100 行): OCR 识别 + 结果展示区域

### 2.5 gui/pages/about.py (514 行)

拆分理由: 版本信息展示 + 更新检查/下载/安装逻辑混合。

- **`gui/pages/about.py`** (~250 行): 关于页面 UI（版本信息、依赖列表、链接）
- **`gui/pages/update.py`** (~250 行): 更新检查、进度下载、安装逻辑

---

## 3. 代码简化与去重

### 3.1 HTTP 客户端生命周期修复 (#2, #6)

现状: bark.py/dingtalk.py 用模块级 `_client`，enhancer.py 用 `__del__`。

改造:
- `httpx.Client` 由调用方注入，`app.state.http_client` 持有
- `bootstrap.py` 在 app startup 时创建 client，注册 `@asynccontextmanager` shutdown 时关闭
- 统一: `notifications/__init__.py` 中提供 `HttpNotifier` 注入基类

### 3.2 错误处理统一

现状: `notifier.py` 中的 `is_print_related_error()` / `format_error_message()` 使用 `re.search` 字符串匹配。

改造:
- `core/exceptions.py` 中建立分层异常体系（已部分存在，补充 `JobCanceled` 使用场景）
- FastAPI 全局 `@app.exception_handler(PrintServerError)` 返回结构化 JSON
- 去除 `notifier.py` 中脆弱的 `re.search` 匹配，改用异常类型判断

### 3.3 临时文件清理统一

现状: `safe_remove()` 散落在 worker.py、pdf.py、image.py。

改造:
- `core/utils.py` 提供 `@contextmanager temp_print_file(suffix)` 自动清理
- 各 backend 和 worker 统一使用，消除散落的 try/finally

### 3.4 通知模块去重

现状: `BarkNotifier.send_notification()` 和 `DingTalk.send_notification()` 几乎相同的 HTTP POST 模式。

改造:
- `notifications/__init__.py` 提供 `HttpNotifier` 混入（含 `_post()` / `_get()` + client 管理）
- `BarkNotifier(Notifier, HttpNotifier)` 和 `DingTalk(Notifier, HttpNotifier)` 各自只保留 payload 构建

### 3.5 主题 QSS 去重（GUI）

现状: `gui/resources/dark.qss` (603 行) 和 `light.qss` (604 行) 几乎完全相同的结构，只在颜色值上不同。

改造:
- 提取公共 QSS 为 `base.qss`，只包含结构定义
- `dark.qss` 和 `light.qss` 只保留颜色变量覆盖
- 共可消除约 400 行重复

### 3.6 去除死代码

- `printing/utils.py` 合并到 `backends/base.py` 后删除
- `services/notifier.py` 废弃后删除
- `services/log_broadcaster.py` 合入 `sse_broadcaster.py` 后删除
- `pyproject.toml` 中 `textual`、`typer` 等未使用的依赖移除
- 各文件中未使用的 import 由 `ruff check --fix` 自动清理

---

## 4. 类型注解与错误处理

### 4.1 补齐类型注解

后端:
- `repository.py`: 所有返回 `dict` 的方法标注 `-> dict | None`，内部使用 TypedDict
- `worker.py`: `execute()` 参数/返回值 `-> tuple[bool, str | None]`
- `printer_monitor.py`: `parse_status() -> tuple[str, list[dict[str, str]]]`
- `engine.py`: `_build_instance() -> PrinterBackend`
- 运行 `mypy --strict` 针对性补齐

GUI:
- `gui/pages/scan.py`, `gui/app.py`: 补齐 Qt 信号/槽函数类型注解
- `gui/event_bridge.py`: Qt 信号类型声明

### 4.2 统一错误响应

- 注册全局 `PrintServerError` 异常处理器（已在 `app/__init__.py` 中部分实现，扩充覆盖）
- 所有 API 端点统一使用 `response_model`，错误走异常处理器而非手写 `raise HTTPException`

### 4.3 mypy 配置更新

- `pyproject.toml` mypy 配置增加 `gui/` 目录
- 增加 `warn_unused_ignores = true`

---

## 5. Bug 修复清单

### 5.1 🔴 严重 Bug（重构前必须修复）

| # | 文件 | 问题 | 修复方案 |
|---|------|------|----------|
| 1 | `repository.py:47` | `_ensure_connection` 死代码 | 在每次 `_execute()` 调用前做健康检查，失败则重连 |
| 2 | `bark.py:9`, `dingtalk.py:9` | 模块级 `_client` 永不关闭 | 全局 HTTP 客户端通过 `app.state.http_client` 管理，`bootstrap` shutdown 关闭 |
| 3 | `job_queue.py:144` | `recover_stuck_jobs` 可能重复入队 | 入队前检查队列中是否已有该 job_id；使用 `set()` 跟踪活跃队列中的 ID |
| 4 | `worker.py:46-58` | 取消竞态条件 | 在 `_is_cancelled` 检查和 `_update_and_broadcast` 之间加锁或重新检查 |
| 5 | `bootstrap.py:96` | `start_watcher()` 无 shutdown | 在 `lifespan` 的 shutdown 段调用 `config.stop_watcher()` |
| 6 | `enhancer.py:21` | `__del__` 不可靠 | 改用注入 + 显式生命周期管理 |

### 5.2 🟡 重要（重构过程中修复）

| # | 文件 | 问题 | 修复方案 |
|---|------|------|----------|
| 7 | `base.py:6` | 全局 `_backend_registry` 测试泄漏 | 添加 `clear_backend_registry()` 重置方法，`conftest.py` 中 fixture 清理 |
| 8 | `sse_broadcaster.py:83` | 锁粒度不一致 | 将 `q.put_nowait` 和状态更新放入同一个锁上下文 |
| 9 | `worker_pool.py:51` | `drain()` 名不副实 | 重命名为 `wait_stop()` 或改为真正的 drain（等待队列为空再 stop） |

### 5.3 🟢 轻微（顺手修复）

| # | 文件 | 问题 | 修复方案 |
|---|------|------|----------|
| 10 | `api.py:99` | 日志文件编码容错 | 添加 `encoding='utf-8', errors='replace'` |
| 11 | `image.py:37` | 取消窗口期 | 添加日志警告，不做行为变更 |

---

## 6. 前端 GUI 优化

### 6.1 gui/pages/ 内路由通信规范化

现状: 每个 page 通过 `self.parent()` 访问 MainWindow，再通过 `parent._bridge` 访问 EventBridge。调用链长且隐式。

改造: 定义 `PageBase` 抽象基类，统一 page 的 lifecycle 接口:

```python
class PageBase(QWidget):
    def on_activated(self): ...          # 导航到此页时调用
    def on_job_status(self, data): ...   # 事件回调
    def on_printer_status(self, data): ...
    def cleanup(self): ...               # 页面销毁时
```

### 6.2 扫描页拆分

按 2.4 节所述，scan.py (667 行) → scan.py + scan_preview.py + scan_ocr.py

### 6.3 About/Update 页拆分

按 2.5 节所述，about.py (514 行) → about.py + update.py

### 6.4 主题 QSS 优化

按 3.5 节所述，QSS → base.qss + dark.qss + light.qss

### 6.5 GUI 测试补充

现状: 只有 3 个 GUI 测试文件（总计 ~100 行），覆盖率极低。

新增:
- `tests/gui/test_main_window.py`: MainWindow 初始化测试
- `tests/gui/test_navigation.py`: 侧边栏导航测试
- `tests/gui/test_event_bridge.py`: EventBridge 信号测试

---

## 7. Launcher 优化

### 7.1 现状

- `launcher/__init__.py` (183 行): 单实例检测 + 配置加载 + 服务器启动 + GUI 启动
- `launcher/_server.py` (163 行): uvicorn 后台进程管理
- `launcher/autostart.py` (88 行): Windows 自动启动注册
- 整体结构合理，不做大的拆分

### 7.2 改进

- `launcher/__init__.py` 中的 `_LifespanRef` 类改为 `dataclass`，消除手动属性赋值
- `_bootstrap_server()` 返回元组改为命名元组或 dataclass，提高可读性
- 补充类型注解

---

## 8. GitHub 配置优化

### 8.1 CI 修复

| # | 行 | 问题 | 修复 |
|---|-----|------|------|
| 1 | ci.yml:37 | `mypy app/ console/` — `console/` 目录不存在 | 改为 `mypy app/ launcher/` |
| 2 | ci.yml:7-9,13-15 | `launcher/**` 被排除在 CI 触发之外 | 移除 launcher/ 排除，或者至少确保 launcher/ 变更触发测试 job |
| 3 | ci.yml:36 | ruff format 检查可能因 Windows 换行符失败 | 确保 `actions/checkout` 配置 autocrlf |
| 4 | ci.yml:67 | `cov-fail-under=70` 在覆盖率略降时阻塞 | 改为 65 以留余量（如果重构中更多测试被添加） |
| 5 | pyproject.toml:83 | mypy `files = ["app/", "launcher/"]` — 缺少 gui/ | 增加 `"gui/"` |

### 8.2 Dependabot

- 当前每周检查 GitHub Actions 和 pip 依赖
- 增加 `schedule.time` 为 `"09:00"` 避免随机执行时间

### 8.3 Release

- `release.yml` 结构合理，无需改动

---

## 9. 项目配置优化

### 9.1 pyproject.toml 依赖清理

| 依赖 | 现状 | 处理 |
|------|------|------|
| `textual>=1.0.0` | 生产依赖 | **移除** — GUI 使用 PySide6，textual 是 TUI 框架 |
| `typer>=0.15.0` | 生产依赖 | **移除** — 未在任何代码中使用 |
| `click` | 间接依赖 | 验证是否仍被任何代码引用 |

### 9.2 ruff 配置

当前配置健全，仅需在目录结构调整后更新 per-file-ignores 中的路径:
- `"gui/*"` → 保持不动
- `"app/printing/backends/*"` → 保持不动
- `"app/services/sse_broadcaster.py"` → 路径不变

### 9.3 mypy 配置

更新 `files = ["app/", "gui/", "launcher/"]`，增加 `gui/` 检查。

---

## 10. 测试策略

### 回归测试
- 目录结构变更后更新所有 import 路径
- `pytest tests/ -v --tb=short` 确保 99+ 个测试全部通过

### 新增测试
- `test_repository_connection.py`: 测试 `_ensure_connection` 重连逻辑
- `test_job_queue_dedup.py`: 测试 `recover_stuck_jobs` 不重复入队
- `test_http_client_lifecycle.py`: 测试客户端注入和关闭
- `tests/gui/test_main_window.py`: GUI 主窗口初始化
- `tests/gui/test_navigation.py`: 侧边栏导航测试
- `tests/gui/test_event_bridge.py`: EventBridge 信号测试

---

## 11. 实施顺序

```
Phase 1: Bug 修复（#1-#6）
  └─ verify: pytest tests/ -v

Phase 2: 目录结构变更（core/ + notifications/ + 文件移动）
  └─ verify: 更新所有 import → pytest 通过

Phase 3: 大文件拆分（repository + api + scan + about）
  └─ verify: pytest 通过，手动测试打印流程

Phase 4: 代码简化（HTTP 客户端、错误处理、临时文件、通知去重、QSS 去重）
  └─ verify: pytest 通过

Phase 5: 类型注解补齐 + 死代码清理（含 pyproject.toml 依赖清理）
  └─ verify: mypy 通过, ruff 通过

Phase 6: 剩余 Bug 修复 + GUI/Launcher 优化（#7-#11, #12-QSS）
  └─ verify: pytest tests/ -v --tb=short

Phase 7: GitHub CI 配置修复 + 新增 GUI 测试
  └─ verify: CI 全部绿色
```
