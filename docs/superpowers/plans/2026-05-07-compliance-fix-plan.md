# 项目合规修复计划

## P0 — 阻塞 Bug
- 添加 JSON `/admin/api/stats` 端点供 dashboard 使用
- 修复 `show_snackbar` 使用 `page.snack_bar` 而非 `page.show_dialog()`
- Dashboard 数据加载失败后自动重试
- 删除死代码 `gui/child_process.py`

## P1 — GUI 规范合规
- SSE 事件订阅：dashboard + job_manager 实时更新
- 所有页面空/加载/错误状态覆盖
- 分页控件 handler + 批量操作 handler
- 设置页：生成密钥按钮
- 关于页：构建时间 + 版本

## P2 — 后端规范合规
- mypy strict 配置
- os.path → pathlib 清理
- Web 后台模板清