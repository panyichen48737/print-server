# 研究发现

## 架构分析

### 当前任务处理链（4 层）

```
Upload → JobQueue(queue.Queue + cancelled集 + queued集 + 2 把锁)
              ↓
        WorkerPool(ThreadPoolExecutor)         ← 只做 start/stop/wait_stop
              ↓
        JobWorker × N (CoInitialize)           ← while 循环取 job
              ↓
        JobExecutor(ThreadPoolExecutor(w=1))   ← 每 worker 持有 1 个线程池做超时
              ↓
        RetryHandler                           ← for attempt in range(max_retries+1)
              ↓
        PrintEngine → backends.py
```

**发现**：
- `WorkerPool` 核心逻辑只有 `start()` 和 `stop()`，共 40 行
- `JobExecutor` 内部 `ThreadPoolExecutor(max_workers=1)` 唯一作用是 `fut.result(timeout=1)` 轮询超时
- `RetryHandler` 整个类 30 行，一个 for 循环
- `JobWorker` 的 `while not stop_evt` 循环模式保留但不需要独立类

### 事件系统

```
SSEBroadcaster
  ├─ _subscribers (remote)
  ├─ _event_bus: EventBus (local)
  └─ publish() → 先推 remote，再委托 event_bus.publish()

EventBus
  ├─ _listeners (local callbacks)
  └─ publish() → 遍历 _listeners
```

**发现**：EventBus 只比 SSEBroadcaster 多了 `on/off/publish`，数据结构是 `dict[str, list[Callable]]`，完全可以合并。

### aiosqlite async/sync 混合

```python
self._loop = asyncio.new_event_loop()
self._thread = threading.Thread(target=self._loop.run_forever)

# 所有方法
def get_job(self, job_id):
    return self._sync(self._execute(...))  # async → sync 包装

def _sync(self, coro):
    return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30)
```

所有调用者都是同步的（Worker 线程、FastAPI 路由），没有人用 async 方式调用。这套 async 包装完全多余。

### 安装器现状

- 已有 `installer.iss`（Inno Setup 6.x + 中文语言 + VCL Style 皮肤）
- 已有 `scripts/build.py`（PyInstaller --onedir + update.zip + 资源复制）
- 已有 Go 更新服务（update_service.exe）
- CI 配置在 .github/workflows/

### GUI 功能结构

7 个导航页面（Sidebar）：
1. 仪表盘 — 统计卡片 + 最近任务表
2. 快速打印 — 文件选择 + 打印选项 + 批量提交
3. 文档扫描 — 扫描仪功能
4. 任务管理 — 队列 + 历史表格
5. 实时日志 — 日志流
6. 设置 — 7 组配置项（安全/服务器/打印/通知/夸克/更新/关于）
7. 关于 — 版本 + 更新

当前打印选项：打印机、份数、彩色/黑白、双面、纸张大小

无 PDF 渲染器。功能扩展需新增 PyMuPDF。

### 构建脚本问题

`scripts/build.py` 包含 ~50 行 `--hidden-import` 手动列表，每增删模块都需要维护。
