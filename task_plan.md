# 架构简化 + 功能扩展 + 构建优化 计划

## 阶段总览

```
Phase 1: 架构简化（核心）
Phase 2: 功能扩展
Phase 3: CI/CD + 构建脚本优化
```

---

## Phase 1: 架构简化

### 1.1 事件系统合并

SSEBroadcaster 直接持有 `_listeners`，删除 EventBus 类。

改动：`app/services/sse_broadcaster.py`

注意：`gui/event_bridge.py` 引用了 `EventBus` 类型，需要更新。

### 1.2 任务处理层精简

删除 `WorkerPool` / `JobWorker` / `JobExecutor` / `RetryHandler`，逻辑内联到 `JobQueue`。

| 操作 | 文件 |
|------|------|
| 删除 | `app/printing/worker_pool.py` |
| 删除 | `app/printing/worker.py` |
| 重写 | `app/printing/job_queue.py` — 添加 start/stop/worker_loop/execute_job |
| 修改 | `app/bootstrap.py` — 移除 WorkerPool 引用，改调 job_queue.start() |
| 修改 | `launcher/__init__.py` — lifespan 中 worker_pool 引用更新 |
| 修改 | `app/routes/api.py` — 检查 worker_pool 引用 |
| 修改 | `tests/` — 更新相关测试 |

### 1.3 aiosqlite → sqlite3

- JobRepository 去掉 async/sync 混合模式
- 去掉 `_loop` + `_thread` + `_sync()` 包装
- `_execute()` 变同步方法
- 删除 `aiosqlite` 依赖

### 1.4 msgspec → json.dumps()

- `app/routes/system.py` 中替换为 stdlib json

### 1.5 SSE /events 端点检查

GUI 用 WS，iOS 用 WS，确认是否还有任何地方用 SSE /events。若无则删。

---

## Phase 2: 功能扩展

### 2.1 文件格式扩展

- `app/printing/backends/text.py` — TextBackend（txt/csv 转 text → win32print）
- config 允许扩展名列表增加 .txt/.csv
- GUI 文件过滤器增加 .txt/.csv

### 2.2 页码范围

- `app/printing/backends/pdf.py` — 增加 page_range 参数，PyMuPDF 抽取指定页
- GUI quick_print.py 增加页码范围输入框（格式：`1-3,5,7-9`）

### 2.3 多页合一 (N-up)

- `app/printing/backends/pdf.py` — 增加 nup 参数，PyMuPDF 渲染页面 → PIL 拼版 → win32print 打印
- GUI quick_print.py 增加 N-up 下拉选择（1/2/4/6/8/16 页每张）

### 新依赖

- `PyMuPDF` — PDF 页面操作 + 渲染

---

## Phase 3: 构建优化

### 3.1 CI 自动发布

打 tag 时自动：
- PyInstaller 构建
- Inno Setup 打包
- update.zip 生成
- 上传到 GitHub Releases

### 3.2 构建脚本简化

- 用 `--collect-all app` + `--collect-all gui` 替代 50 行 hidden-import
- 动态发现包

---

## 不做的

| 项目 | 理由 |
|------|------|
| 安装器升级（Inno Setup→Squirrel） | Inno Setup 稳定够用 |
| Nuitka 编译 | 20-40 分钟编译，不值得 |
| 代码签名 | 证书要钱，个人项目没必要 |
| 打印预览 | 流程不成熟，iOS 场景用不上 |
| 跨平台 | 确认 Windows only |
| 管理后台 | 已确认删除 |
| winget/chocolatey 分发 | 用户量不够 |

---

## 依赖变化

| 操作 | 包 |
|------|-----|
| 删除 | `aiosqlite` |
| 删除 | `msgspec` |
| 新增 | `PyMuPDF` |

---

## 决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-05-16 | aiosqlite → sqlite3 | 所有调用者都是同步，async 包装多余 |
| 2026-05-16 | 4 层任务包装 → 1 层 JobQueue | 每个类的核心逻辑都不到 50 行 |
| 2026-05-16 | EventBus 合并入 SSEBroadcaster | 50 行代码不值得一个独立类 |
| 2026-05-16 | 功能扩展前后端同步 | GUI 操作都在桌面端，无 Web 页面 |
| 2026-05-16 | CI 自动发布 | 简化发版流程 |
| 2026-05-16 | 跳过安装器升级 | Inno Setup 稳定，投入产出比低 |
