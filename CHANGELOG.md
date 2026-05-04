# Changelog

## [1.0.0] - 2026-05-04

### Added
- Office 文件打印改为 COM 转 PDF → IPP/RAW/Chromium 三阶打印链路
- 版本号自动管理（git describe + 构建时注入）
- PyInstaller 一键构建脚本 `build.py`

### Changed
- OfficeBackend 重写：COM PrintOut → SaveAs2/ExportAsFixedFormat PDF 导出
- PrintEngine 新增 Office → PDF 分流 + 临时文件自动清理
- End-to-end 接口一致性统一（cancel 传 print_engine、响应格式、job_status 事件形状）

### Fixed
- 资源泄漏修复（S SE 订阅者移除、心跳线程安全、httpx 连接池）
- 通知异常日志 + PrinterDiscoveryService 缓存复用
- Config 线程安全 + 统一 config.get() 访问模式

## [0.9.0] - 2026-04-28

### Added
- Textual TUI 替代 Rich，HTMX 管理后台交互升级
- 服务层提取：SSEBroadcaster / PrintService / HeartbeatMonitor
- IPP Everywhere 直送 + RAW Spooler + Chromium 三阶 PDF 打印
- PrinterDiscoveryService 打印机自动发现

### Changed
- 模块化架构重构：EventBus → SSEBroadcaster 合并
- QueueManager 拆分职责到 JobQueue/WorkerPool
- httpx 连接池替代 requests

### Fixed
- PrintService 移除 / WorkerPool 职责拆分
- 多代理并行修复：资源泄漏/取消通知/SSE TTL

## [0.8.0] - 2026-04-15

### Added
- Bark 通知推送支持（iOS 原生推送）
- Quark API 图像增强集成
- 打印机状态监控 + 实时推送
- Web 上传页面 + 批量上传
- iOS Scriptable 多文件分享支持

### Changed
- 打印引擎重构：提取 COM 上下文管理器、拆分上帝方法
- handle_file_upload 返回结构化 UploadResult
- DaisyUI 3.0 前端升级 + Financial Dashboard 配色

### Fixed
- Quark API 适配（认证参数、字段映射、自动压缩）
- nssm 安装路径问题 + 控制台抖动
- 子进程启动 WinError 87

## [0.1.0] - 2026-03-20

### Added
- iOS Cloud Print Server 初始版本
- win32com Office 打印（Word/Excel/PPT）
- IPP 直接打印
- 飞书通知集成
- PyInstaller 打包支持
- 开机自启管理（nssm + schtasks）
- iOS Shortcuts / Scriptable 集成
