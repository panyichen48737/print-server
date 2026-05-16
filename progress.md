# 会话日志

## 2026-05-16 — 架构简化规划

### 背景

用户询问整个项目是否有更好的方案。在讨论 6 个维度后，确定「简化架构（第 1 项）」最值得做，「功能扩展（第 6 项）」待定。

### 分析

- 审视了整个任务处理链（WorkerPool → JobWorker → JobExecutor → RetryHandler → PrintEngine）
- 发现 4 层的功能重叠和冗余（每个 JobExecutor 持有一个 ThreadPoolExecutor）
- 发现 EventBus + SSEBroadcaster 的双层委托可以合并
- 确认 Office COM + win32print 方案在 Windows 上是正确的选择，不动

### 决策

- **删除** `WorkerPool` / `JobWorker` / `JobExecutor` / `RetryHandler`
- 逻辑内联到 `JobQueue`
- **合并** `EventBus` 到 `SSEBroadcaster`
- **去掉** `queued_ids` 内存集合
- **保留** win32print + Office COM

### 待确认

- 功能扩展的具体方向尚未确定，等 Phase 1-2 完成后讨论
